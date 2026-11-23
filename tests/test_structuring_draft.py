"""문서 정형화 초안 → 확정 (SWFR.CON.007 · SWFR.PIP.001 · SWFR.PIP.002).

우리 요구사항정의서(IM-001)를 DOCX 로 만들어 올리면 41건이 초안으로 뽑히고,
확정하면 산출물 항목과 요구사항으로 적재된다. 모델은 fake 다. 실모델은
test_structuring_live.py 가 따로 본다.
"""

import io
import re
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.ai.port import LlmResult
from app.common import errors
from app.db import tx
from app.document import draft_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
IM001 = Path(__file__).resolve().parent.parent / "docs/10-requirements/IM-001-요구사항정의서.md"
ROW_RE = re.compile(r"^\|\s*((?:SWFR|QUR|SER)\.[A-Z]{3}\.\d{3})\s*\|", re.MULTILINE)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _md_to_docx(markdown: str) -> bytes:
    """마크다운을 DOCX 로 옮긴다. 표는 표로, 나머지 줄은 문단으로. 파서 시험용이다."""
    from docx import Document

    doc = Document()
    table: list[list[str]] = []

    def flush() -> None:
        if not table:
            return
        width = max(len(r) for r in table)
        t = doc.add_table(rows=len(table), cols=width)
        for i, row in enumerate(table):
            for j, cell in enumerate(row):
                t.cell(i, j).text = cell
        table.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            table.append(cells)
            continue
        flush()
        if line:
            doc.add_paragraph(line.lstrip("# ").strip())
    flush()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _xlsx_bytes(rows: list[list[str]], sheet: str = "Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cleanup() -> None:
    """이 스위트가 만든 것만 지운다. 문서, 문서에서 온 요구사항·산출물 버전, 그 색인."""
    with tx() as cur:
        cur.execute(
            """
            delete from doc_chunk
             where source_type = 'REQUIREMENT'
               and source_id in (select id from requirement
                                  where project_id = %s and source_kind = 'DOCUMENT')
            """,
            (PID,),
        )
        cur.execute("delete from requirement_baseline where project_id = %s", (PID,))
        cur.execute(
            "delete from requirement where project_id = %s and source_kind = 'DOCUMENT'", (PID,)
        )
        cur.execute(
            "delete from work_product where project_id = %s and source_kind = 'DOCUMENT'", (PID,)
        )
        # 문서 버전이 현행을 밀어냈으면 시드 자리(버전 0)를 다시 현행으로 올린다.
        cur.execute(
            """
            update work_product w
               set is_current = true, updated_at = now()
             where w.project_id = %s and w.version = '0' and not w.is_current
               and not exists (select 1 from work_product c
                                where c.project_id = w.project_id and c.type = w.type
                                  and c.is_current)
            """,
            (PID,),
        )
        cur.execute(
            "delete from doc_chunk where project_id = %s and source_type = 'DOCUMENT_UPLOAD'",
            (PID,),
        )
        cur.execute("delete from document_upload where project_id = %s", (PID,))


@pytest.fixture
def as_pm(client, client_token):
    token = client_token("r3")
    _cleanup()
    yield token
    _cleanup()


def _upload(client, token: str, name: str, data: bytes) -> dict:
    res = client.post(
        f"/api/projects/{PID}/documents",
        files={"file": (name, data, "application/octet-stream")},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()


def _draft(client, token: str, doc_id: str) -> dict:
    res = client.get(f"/api/documents/{doc_id}/draft", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def im001(client, as_pm) -> dict:
    """IM-001 을 DOCX 로 올린 문서. 표 41행이 그대로 살아 있어야 한다."""
    return _upload(client, as_pm, "IM-001-요구사항정의서.docx",
                   _md_to_docx(IM001.read_text(encoding="utf-8")))


@requires_db
def test_im001_upload_drafts_41_requirements(client, as_pm, im001):
    assert im001["status"] == "STRUCTURED"
    assert im001["draftAvailable"] is True
    assert im001["workProductId"] is None

    draft = _draft(client, as_pm, im001["id"])
    assert draft["status"] == "PROPOSED"
    assert draft["suggestedType"] == "REQUIREMENTS_SPEC"
    assert draft["confidence"] > 0.5
    assert draft["rejectedTypeRaw"] is None
    assert draft["title"] == "AX Link 요구사항정의서 (IM-001)"
    assert draft["version"] == "0.4.1"
    assert draft["authoredDate"] == "2026-11-23"
    assert "pmActivity" not in draft and "siActivity" not in draft  # 활동은 유형이 정한다

    codes = [r["code"] for r in draft["requirements"]]
    assert len(codes) == 41
    # 문서에 적힌 코드와 정확히 같아야 한다. 규칙이 지어낸 코드가 있으면 여기서 걸린다.
    assert codes == ROW_RE.findall(IM001.read_text(encoding="utf-8"))
    assert {r["priority"] for r in draft["requirements"]} == {"MUST"}
    assert all(r["title"] and r["body"] for r in draft["requirements"])


def _confirm_body(draft: dict, **overrides) -> dict:
    body = {
        "type": draft["suggestedType"],
        "title": draft["title"],
        "version": draft["version"],
        "authoredDate": draft["authoredDate"],
        "requirements": draft["requirements"],
    }
    body.update(overrides)
    return body


@requires_db
def test_confirm_places_work_product_but_not_requirements(client, as_pm, im001):
    draft = _draft(client, as_pm, im001["id"])
    res = client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        json=_confirm_body(draft),
        headers=_auth(as_pm),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # 요구사항은 초안 확정으로 만들지 않는다. 요구사항 기준선(제출 → 발주기관 확정)으로만
    # 들어간다(GH-139). 용역사가 확정한 초안이 곧바로 확정 요구사항처럼 보이면 안 된다
    assert body["createdRequirementIds"] == []
    assert body["indexedChunkCount"] == 0

    # 산출물 자리: 요구사항정의서 0.4 가 현행이 됐다.
    items = client.get(f"/api/projects/{PID}/work-products", headers=_auth(as_pm)).json()["items"]
    spec = next(i for i in items if i["type"] == "REQUIREMENTS_SPEC")
    assert spec["id"] == body["workProductId"]
    assert spec["version"] == "0.4.1" and spec["status"] == "SUBMITTED"
    assert spec["title"] == draft["title"]
    assert spec["fileUri"]  # 올린 원본을 가리킨다
    with tx() as cur:
        cur.execute(
            "select source_kind, document_upload_id::text as doc, authored_at::text as at "
            "from work_product where id = %s",
            (body["workProductId"],),
        )
        row = cur.fetchone()
    assert row == {"source_kind": "DOCUMENT", "doc": im001["id"], "at": "2026-11-23"}

    # 요구사항 목록에는 아무것도 들어가지 않았다
    page = client.get(
        f"/api/projects/{PID}/requirements?page=0&size=100", headers=_auth(as_pm)
    ).json()
    assert [r for r in page["content"] if r["source"]["tool"] == "UPLOAD"] == []

    # 문서와 초안의 상태가 넘어갔고, 목록에서 "초안 확인" 이 내려갔다.
    listed = client.get(f"/api/projects/{PID}/documents", headers=_auth(as_pm)).json()["content"]
    doc = next(d for d in listed if d["id"] == im001["id"])
    assert doc["status"] == "CONFIRMED"
    assert doc["draftAvailable"] is False
    assert doc["workProductId"] == body["workProductId"]
    assert _draft(client, as_pm, im001["id"])["status"] == "CONFIRMED"

    # 두 번 확정은 막는다. 같은 41건이 또 들어가면 안 된다.
    again = client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        json=_confirm_body(draft),
        headers=_auth(as_pm),
    )
    assert again.status_code == 409
    assert again.json()["code"] == "DRAFT_ALREADY_DECIDED"


@requires_db
def test_overriding_the_suggested_type_is_recorded(client, as_pm, im001):
    """제안과 다르게 확정하면 MANUAL_OVERRIDE 다. 규칙·모델의 오답 기록이 된다."""
    draft = _draft(client, as_pm, im001["id"])
    res = client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        # 예전 화면처럼 활동을 보내도 받지 않는다
        json=_confirm_body(draft, type="SOFTWARE_DESIGN", requirements=[], pmActivity="PM_4",
                           siActivity=None, workProductStatus="SUBMITTED"),
        headers=_auth(as_pm),
    )
    assert res.status_code == 200, res.text
    assert res.json()["createdRequirementIds"] == []
    assert _draft(client, as_pm, im001["id"])["status"] == "MANUAL_OVERRIDE"

    items = client.get(f"/api/projects/{PID}/work-products", headers=_auth(as_pm)).json()["items"]
    design = next(i for i in items if i["type"] == "SOFTWARE_DESIGN")
    assert design["status"] == "SUBMITTED" and design["approvedAt"] is None
    assert (design["pmActivity"], design["siActivity"]) == (None, "SI_3")  # 설계서는 SI 설계


@requires_db
def test_확정은_곧_제출이고_임시_등록은_없다(client, as_pm, im001):
    """초안 확정 = 산출물 제출본 등록(DEC-14 (a)). 예전처럼 DRAFT 를 고르면 거절한다.

    조용히 제출본으로 바꾸면 임시로 둘 생각이던 사람의 문서가 발주기관 검토 대상이 된다.
    """
    draft = _draft(client, as_pm, im001["id"])
    res = client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        json=_confirm_body(draft, workProductStatus="DRAFT"),
        headers=_auth(as_pm),
    )
    assert res.status_code == 400
    assert "제출본" in res.json()["message"]
    assert _draft(client, as_pm, im001["id"])["status"] == "PROPOSED"


@requires_db
def test_확정으로는_승인할_수_없다(client, as_pm, im001):
    """확정은 산출물 등록이다. 승인은 발주기관이 따로 한다.

    용역사가 APPROVED 로 확정하던 길을 막는다.
    """
    draft = _draft(client, as_pm, im001["id"])
    res = client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        json=_confirm_body(draft, workProductStatus="APPROVED"),
        headers=_auth(as_pm),
    )
    assert res.status_code == 400
    assert "승인" in res.json()["message"]
    # 막혔으니 초안은 그대로 확인 대기다
    assert _draft(client, as_pm, im001["id"])["status"] == "PROPOSED"


@requires_db
def test_reject_closes_the_draft(client, as_pm, im001):
    res = client.post(f"/api/documents/{im001['id']}/draft/reject", headers=_auth(as_pm))
    assert res.status_code == 204

    listed = client.get(f"/api/projects/{PID}/documents", headers=_auth(as_pm)).json()["content"]
    doc = next(d for d in listed if d["id"] == im001["id"])
    assert doc["status"] == "REJECTED" and doc["draftAvailable"] is False
    assert _draft(client, as_pm, im001["id"])["status"] == "REJECTED"

    # 반려한 뒤에는 확정도 반려도 다시 안 된다.
    draft = _draft(client, as_pm, im001["id"])
    assert client.post(
        f"/api/documents/{im001['id']}/draft/confirm",
        json=_confirm_body(draft, type="REQUIREMENTS_SPEC"),
        headers=_auth(as_pm),
    ).status_code == 409
    assert client.post(
        f"/api/documents/{im001['id']}/draft/reject", headers=_auth(as_pm)
    ).status_code == 409

    # 표준 모델에는 아무것도 안 들어갔다.
    with tx() as cur:
        cur.execute(
            "select count(*) as n from requirement "
            "where project_id = %s and source_kind = 'DOCUMENT'",
            (PID,),
        )
        assert cur.fetchone()["n"] == 0


@requires_db
def test_confirm_rejects_bad_values_before_the_schema_does(client, as_pm, im001):
    draft = _draft(client, as_pm, im001["id"])
    url = f"/api/documents/{im001['id']}/draft/confirm"

    bad_type = client.post(url, json=_confirm_body(draft, type="MEMO"), headers=_auth(as_pm))
    assert bad_type.status_code == 400 and "유형" in bad_type.json()["message"]

    dup = list(draft["requirements"][:2])
    dup[1] = {**dup[1], "code": dup[0]["code"]}
    dup_res = client.post(url, json=_confirm_body(draft, requirements=dup), headers=_auth(as_pm))
    assert dup_res.status_code == 400 and "겹칩니다" in dup_res.json()["message"]

    bad_status = client.post(
        url, json=_confirm_body(draft, workProductStatus="NONE"), headers=_auth(as_pm)
    )
    assert bad_status.status_code == 400

    bad_date = client.post(
        url, json=_confirm_body(draft, authoredDate="2026-13-40"), headers=_auth(as_pm)
    )
    assert bad_date.status_code == 400

    # 전부 거절됐으니 초안은 아직 제안 상태다.
    assert _draft(client, as_pm, im001["id"])["status"] == "PROPOSED"


@requires_db
def test_same_version_reconfirm_updates_in_place_and_new_version_stacks(client, as_pm):
    """같은 버전을 다시 올리면 그 행을 고치고, 다른 버전이면 앞 버전을 내리고 쌓는다."""
    first = _upload(client, as_pm, "WBS.xlsx", _xlsx_bytes([["작업", "가중치"], ["설계", "0.3"]]))
    draft = _draft(client, as_pm, first["id"])
    assert draft["suggestedType"] == "PROJECT_PLAN"
    a = client.post(
        f"/api/documents/{first['id']}/draft/confirm",
        json=_confirm_body(draft, title="사업수행계획서", version="1.0", requirements=[]),
        headers=_auth(as_pm),
    ).json()

    second = _upload(client, as_pm, "WBS-수정.xlsx",
                     _xlsx_bytes([["작업", "가중치"], ["설계", "0.4"]]))
    draft = _draft(client, as_pm, second["id"])
    b = client.post(
        f"/api/documents/{second['id']}/draft/confirm",
        json=_confirm_body(draft, type="PROJECT_PLAN", title="사업수행계획서(정정)", version="1.0",
                           requirements=[]),
        headers=_auth(as_pm),
    ).json()
    assert b["workProductId"] == a["workProductId"]

    third = _upload(client, as_pm, "WBS-2차.xlsx",
                    _xlsx_bytes([["작업", "가중치"], ["구현", "0.5"]]))
    draft = _draft(client, as_pm, third["id"])
    c = client.post(
        f"/api/documents/{third['id']}/draft/confirm",
        json=_confirm_body(draft, type="PROJECT_PLAN", title="사업수행계획서", version="1.1",
                           requirements=[]),
        headers=_auth(as_pm),
    ).json()
    assert c["workProductId"] != a["workProductId"]

    with tx() as cur:
        cur.execute(
            """
            select version, is_current, title, document_upload_id::text as doc
              from work_product where project_id = %s and type = 'PROJECT_PLAN'
             order by version
            """,
            (PID,),
        )
        rows = cur.fetchall()
    by_version = {r["version"]: r for r in rows}
    assert by_version["1.0"]["is_current"] is False
    assert by_version["1.0"]["title"] == "사업수행계획서(정정)"
    assert by_version["1.0"]["doc"] == second["id"]
    assert by_version["1.1"]["is_current"] is True and by_version["1.1"]["doc"] == third["id"]
    assert sum(1 for r in rows if r["is_current"]) == 1


class _Stub:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, system: str, user: str) -> LlmResult:
        return LlmResult(text=self._text, model="stub")


class _Down:
    def complete(self, system: str, user: str) -> LlmResult:
        raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 에 닿지 못했습니다")


_PLAIN = [["항목", "값"], ["일시", "9월 1일"], ["장소", "회의실"]]


@requires_db
def test_llm_picks_the_type_only_when_rules_cannot(client, as_pm, monkeypatch):
    monkeypatch.setattr(
        draft_service, "llm_port", lambda: _Stub("<think>...</think>\nMEETING_RECORD")
    )
    doc = _upload(client, as_pm, "memo.xlsx", _xlsx_bytes(_PLAIN))
    draft = _draft(client, as_pm, doc["id"])
    assert draft["suggestedType"] == "MEETING_RECORD"
    assert draft["confidence"] == draft_service.LLM_CONFIDENCE  # 모델 판정은 규칙보다 낮게 본다
    assert draft["title"] == "시트: Sheet1"  # 제목은 규칙이 이미 정했으니 모델에 안 묻는다
    with tx() as cur:
        cur.execute(
            "select model from structuring_draft where document_upload_id = %s", (doc["id"],)
        )
        assert cur.fetchone()["model"] == "stub"


@requires_db
def test_unparseable_llm_answer_leaves_the_type_open(client, as_pm):
    """기본 fake 모델은 코드를 답하지 않는다. 그러면 유형은 비고 사람이 고른다."""
    doc = _upload(client, as_pm, "memo.xlsx", _xlsx_bytes(_PLAIN))
    draft = _draft(client, as_pm, doc["id"])
    assert draft["suggestedType"] is None
    assert draft["confidence"] == 0.0
    assert draft["rejectedTypeRaw"]


@requires_db
def test_llm_outage_still_leaves_a_rule_only_draft(client, as_pm, monkeypatch):
    monkeypatch.setattr(draft_service, "llm_port", lambda: _Down())
    doc = _upload(client, as_pm, "memo.xlsx", _xlsx_bytes(_PLAIN))
    assert doc["status"] == "STRUCTURED" and doc["draftAvailable"] is True
    assert "유형 판별" in doc["error"]
    draft = _draft(client, as_pm, doc["id"])
    assert draft["suggestedType"] is None and draft["rejectedTypeRaw"] is None


@requires_db
def test_rule_decided_type_never_calls_the_llm(client, as_pm, monkeypatch, im001):
    """규칙이 정했으면 모델은 부르지 않는다. 불렀다면 여기서 터진다."""

    def boom():
        raise AssertionError("규칙이 정한 문서에 LLM 을 불렀다")

    monkeypatch.setattr(draft_service, "llm_port", boom)
    doc = _upload(client, as_pm, "WBS.xlsx", _xlsx_bytes([["작업", "가중치"]], sheet="WBS"))
    assert _draft(client, as_pm, doc["id"])["suggestedType"] == "PROJECT_PLAN"


@requires_db
def test_unknown_document_has_no_draft(client, as_pm):
    unknown = "00000000-0000-4000-8000-000000000000"
    res = client.get(f"/api/documents/{unknown}/draft", headers=_auth(as_pm))
    assert res.status_code == 404


@requires_db
def test_im001_명세서로_기준선을_만들면_41건이_위치와_함께_문제없이_나온다(
    client, client_token, as_pm, im001
):
    """실제 요구사항정의서로 기준선 1단계를 돈다(GH-139). 초안 확정을 거치지 않아도 된다."""
    base = f"/api/projects/{PID}/requirement-baseline"
    created = client.post(base, json={"documentId": im001["id"]}, headers=_auth(as_pm))
    assert created.status_code == 201, created.text
    b = created.json()
    codes = [i["code"] for i in b["items"]]
    assert codes == ROW_RE.findall(IM001.read_text(encoding="utf-8"))
    assert b["blockingCount"] == 0 and not any(i["problems"] for i in b["items"])
    assert all(i["location"].startswith("표 ") for i in b["items"])
    assert b["sourceDocVersion"] == "0.4.1"

    sub = client.post(f"{base}/{b['id']}/submit", headers=_auth(as_pm))
    assert sub.status_code == 200, sub.text
    done = client.post(f"{base}/{b['id']}/confirm", json={},
                       headers=_auth(client_token("r2")))
    assert done.status_code == 200, done.text
    assert sum(done.json()["counts"].values()) == 41
