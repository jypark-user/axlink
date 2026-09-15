"""문서 업로드 → 파싱 → 저장. 실제 파일을 만들어 올린다.

박PM 시나리오의 "비정형 산출물을 올리면 시스템이 읽는다" 경로다.
"""

import io
import zipfile
from urllib.parse import unquote

import pytest
from openpyxl import Workbook

from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _xlsx_bytes(marker: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "WBS"
    ws.append(["작업", "가중치", "진척"])
    ws.append([marker, 0.2, 1.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hwpx_bytes() -> bytes:
    """표 하나짜리 최소 HWPX. scripts/verify_doc_parsers.py 와 같은 구조다."""
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    hs = "http://www.hancom.co.kr/hwpml/2011/section"

    def p(t: str) -> str:
        return f"<hp:p><hp:run><hp:t>{t}</hp:t></hp:run></hp:p>"

    def tc(t: str) -> str:
        return f"<hp:tc><hp:subList>{p(t)}</hp:subList></hp:tc>"

    rows = [["산출물", "담당"], ["요구사항정의서", "PM"]]
    tbl = "<hp:tbl>" + "".join(
        "<hp:tr>" + "".join(tc(c) for c in r) + "</hp:tr>" for r in rows
    ) + "</hp:tbl>"
    section = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hs:sec xmlns:hp="{hp}" xmlns:hs="{hs}">{p("산출물 현황")}{tbl}</hs:sec>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/manifest.xml", '<?xml version="1.0"?><manifest/>')
        z.writestr("Contents/header.xml", f'<?xml version="1.0"?><hh:head xmlns:hh="{hp}"/>')
        z.writestr("Contents/section0.xml", section)
    return buf.getvalue()


@pytest.fixture
def as_pm(client, client_token):
    """박PM(용역사) 토큰. 앞뒤로 이 사업의 문서를 비워 남은 데이터가 테스트를 깨지 않게 한다."""
    token = client_token("r3")
    _purge(client, token)
    yield token
    _purge(client, token)


def _purge(client, token: str) -> None:
    from app.db import tx

    with tx() as cur:
        # 청크까지 지운다. 업로드만 지우면 색인이 남아 다음 시험의 셈을 흐린다.
        cur.execute(
            "delete from doc_chunk where project_id = %s and source_type = 'DOCUMENT_UPLOAD'",
            (PID,),
        )
        cur.execute("delete from document_upload where project_id = %s", (PID,))


def _upload(client, token: str, name: str, data: bytes, mime: str = "application/octet-stream"):
    return client.post(
        f"/api/projects/{PID}/documents",
        files={"file": (name, data, mime)},
        headers=_auth(token),
    )


@requires_db
def test_xlsx_upload_is_parsed_and_stored(client, as_pm):
    res = _upload(client, as_pm, "WBS.xlsx", _xlsx_bytes("요구사항 정의"))
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["fileName"] == "WBS.xlsx"
    # 읽고 나면 바로 초안까지 만든다. 사람이 확인할 초안이 생긴 상태가 STRUCTURED 다.
    assert body["status"] == "STRUCTURED"
    assert body["draftAvailable"] is True
    assert body["extractedCharCount"] > 0
    assert body["error"] is None
    assert body["uploadedBy"]  # 올린 사람 이름이 붙는다

    text = client.get(f"/api/documents/{body['id']}/text", headers=_auth(as_pm)).json()
    # SWFR.CON.007 — 표는 행·열 구조가 남아야 한다.
    assert "| 작업 | 가중치 | 진척 |" in text["text"]
    assert "요구사항 정의" in text["text"]


@requires_db
def test_hwpx_table_survives_upload(client, as_pm):
    """한글 문서의 표 셀 구조가 업로드 경로를 지나도 유지되는지 — RSK-010."""
    res = _upload(client, as_pm, "산출물현황.hwpx", _hwpx_bytes())
    assert res.status_code == 201, res.text
    doc_id = res.json()["id"]

    text = client.get(f"/api/documents/{doc_id}/text", headers=_auth(as_pm)).json()["text"]
    assert "| 산출물 | 담당 |" in text
    assert "| 요구사항정의서 | PM |" in text


@requires_db
def test_same_content_is_rejected(client, as_pm):
    """파일명을 바꿔 다시 올려도 내용이 같으면 같은 문서다."""
    data = _xlsx_bytes("중복확인")
    assert _upload(client, as_pm, "첫번째.xlsx", data).status_code == 201

    again = _upload(client, as_pm, "이름만다름.xlsx", data)
    assert again.status_code == 409
    assert again.json()["code"] == "DOCUMENT_DUPLICATE"


@requires_db
def test_unsupported_extension_is_rejected(client, as_pm):
    res = _upload(client, as_pm, "메모.txt", b"aaaa")
    assert res.status_code == 400
    assert "HWP" in res.json()["message"]


@requires_db
def test_empty_file_is_rejected(client, as_pm):
    assert _upload(client, as_pm, "빈파일.pdf", b"").status_code == 400


@requires_db
def test_broken_file_is_recorded_as_failed(client, as_pm):
    """파서가 죽어도 업로드 기록은 남는다 — 왜 실패했는지 화면에서 보여야 한다."""
    res = _upload(client, as_pm, "깨진문서.docx", b"not a real docx at all")
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "FAILED"
    assert body["error"]


@requires_db
def test_list_is_paged_and_newest_first(client, as_pm):
    _upload(client, as_pm, "하나.xlsx", _xlsx_bytes("하나"))
    _upload(client, as_pm, "둘.xlsx", _xlsx_bytes("둘"))

    page = client.get(f"/api/projects/{PID}/documents?page=0&size=20", headers=_auth(as_pm)).json()
    assert page["totalElements"] == 2
    assert [d["fileName"] for d in page["content"]] == ["둘.xlsx", "하나.xlsx"]


@requires_db
def test_other_project_is_denied(client, client_token):
    """배정되지 않은 사업에는 못 올린다 — SER.SEC.003."""
    other = "c0000000-0000-4000-8000-000000000099"
    res = client.post(
        f"/api/projects/{other}/documents",
        files={"file": ("x.xlsx", _xlsx_bytes("x"), "application/octet-stream")},
        headers=_auth(client_token("r3")),
    )
    assert res.status_code == 403


@requires_db
def test_extracted_document_is_indexed(client, as_pm):
    """올린 문서는 바로 색인된다 — 전문 열람과 AI 질의가 같은 청크를 쓴다."""
    res = _upload(client, as_pm, "색인대상.xlsx", _xlsx_bytes("색인 확인용 본문"))
    doc_id = res.json()["id"]

    chunks = client.get(f"/api/documents/{doc_id}/chunks", headers=_auth(as_pm)).json()
    assert chunks["totalElements"] >= 1
    assert chunks["content"][0]["index"] == 0
    joined = "".join(c["content"] for c in chunks["content"])
    assert "색인 확인용 본문" in joined


@requires_db
def test_chunks_of_unknown_document_is_404(client, as_pm):
    unknown = "00000000-0000-4000-8000-000000000000"
    res = client.get(f"/api/documents/{unknown}/chunks", headers=_auth(as_pm))
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"


@requires_db
def test_missing_route_returns_our_error_envelope(client, as_pm):
    """없는 API 가 INTERNAL 로 둔갑하면 진단이 어려워진다."""
    res = client.get("/api/projects/없는것/그런거", headers=_auth(as_pm))
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"


@requires_db
def test_original_file_can_be_downloaded(client, as_pm):
    """원본을 그대로 돌려줘야 추출 결과와 대조할 수 있다."""
    data = _xlsx_bytes("대조용")
    doc_id = _upload(client, as_pm, "원본대조.xlsx", data).json()["id"]

    res = client.get(f"/api/documents/{doc_id}/content", headers=_auth(as_pm))
    assert res.status_code == 200
    assert res.content == data  # 바이트가 그대로다

    # 한글 파일명은 RFC 5987 로 퍼센트 인코딩돼 나간다 — 브라우저가 이걸 되돌린다.
    disposition = unquote(res.headers["content-disposition"])
    assert "원본대조.xlsx" in disposition


@requires_db
def test_delete_removes_document_and_chunks(client, as_pm):
    doc_id = _upload(client, as_pm, "지울것.xlsx", _xlsx_bytes("지울 내용")).json()["id"]
    assert client.get(f"/api/documents/{doc_id}/chunks", headers=_auth(as_pm)).json()[
        "totalElements"
    ] > 0

    assert client.delete(f"/api/documents/{doc_id}", headers=_auth(as_pm)).status_code == 204
    assert client.get(f"/api/documents/{doc_id}/text", headers=_auth(as_pm)).status_code == 404

    from app.db import tx

    with tx() as cur:
        cur.execute(
            "select count(*) as n from doc_chunk where source_id = %s", (doc_id,)
        )
        assert cur.fetchone()["n"] == 0


@requires_db
def test_delete_allows_reupload_of_same_file(client, as_pm):
    """지운 뒤 같은 파일을 다시 올릴 수 있어야 한다 — 보관 원본까지 지워지는지 확인."""
    data = _xlsx_bytes("재업로드")
    first = _upload(client, as_pm, "재업로드.xlsx", data).json()["id"]
    client.delete(f"/api/documents/{first}", headers=_auth(as_pm))

    again = _upload(client, as_pm, "재업로드.xlsx", data)
    assert again.status_code == 201
    assert again.json()["status"] == "STRUCTURED"
