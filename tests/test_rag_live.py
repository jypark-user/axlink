"""실모델 질의 검증. Ollama 에 bge-m3 와 설정된 LLM 이 있을 때만 돈다.

저장소 문서 몇 개를 실제 임베딩으로 색인하고, 대표 질문을 API 로 흘려 라우팅·게이트·
출처가 실제 모델에서도 성립하는지 본다. 문장 품질은 여기서 재지 않는다. 보는 것은
1순위 근거가 맞는 문서인지, 관계없는 질문이 게이트에 막히는지, 집계 질문이 인포그래픽으로
가고 답의 숫자가 집계 값 안에 있는지다. ARC-010 의 실측 표는 이 시험의 출력이다.
"""

import json
import uuid
from pathlib import Path

import httpx
import pytest

from app.ai.embedding import embedding_port
from app.config import settings
from app.db import tx
from app.rag import indexing
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID("7a1d2b3c-4e5f-4a6b-8c7d-9e0f1a2b3c4d")
DOCS = {
    "ARC-003 도구 연동방식": "docs/20-design/ARC-003-도구-연동방식.md",
    "진척률 산정체계": "docs/20-design/진척률-산정체계.md",
    "IM-001 요구사항정의서": "docs/10-requirements/IM-001-요구사항정의서.md",
    "인프라 배치방안": "docs/20-design/인프라-배치방안.md",
    "README": "README.md",
}


def _models_ready() -> bool:
    try:
        res = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        names = {m.get("name", "").split(":")[0] for m in res.json().get("models", [])}
    except Exception:
        return False
    return {settings.llm_model.split(":")[0], settings.embedding_model.split(":")[0]} <= names


live = pytest.mark.skipif(
    not _models_ready(),
    reason=f"Ollama 에 {settings.llm_model} 과 {settings.embedding_model} 이 있어야 한다",
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _events(res) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    name, data = "message", []
    for line in [*res.iter_lines(), ""]:
        if line == "":
            if data:
                out.append((name, json.loads("\n".join(data))))
            name, data = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    return out


@pytest.fixture(scope="module")
def real_models():
    """이 모듈 동안만 실제 포트를 쓴다. conftest 가 Fake 로 바꿔 둔 것을 되돌린다."""
    before = (settings.embedding_provider, settings.llm_provider)
    settings.embedding_provider = "ollama"
    settings.llm_provider = "ollama"
    yield
    settings.embedding_provider, settings.llm_provider = before


@pytest.fixture(scope="module")
def indexed_docs(real_models):
    sources = [
        indexing.IndexSource(
            source_type="DOCUMENT_UPLOAD",
            source_id=str(uuid.uuid5(NS, path)),
            project_id=PID,
            title=title,
            body=(ROOT / path).read_text(encoding="utf-8"),
            uri="",
        )
        for title, path in DOCS.items()
    ]
    with tx() as cur:
        indexing.reindex(cur, embedding_port(), sources)
    yield
    with tx() as cur:
        for source in sources:
            cur.execute("delete from doc_chunk where source_id = %s", (source.source_id,))


@pytest.fixture
def ask(client, client_token, indexed_docs):
    token = client_token("r2")
    created = client.post(
        "/api/conversations", json={"title": "실모델", "projectScope": [PID]}, headers=_auth(token)
    ).json()

    def _ask(question: str) -> dict:
        with client.stream(
            "POST",
            f"/api/conversations/{created['id']}/messages",
            json={"question": question, "projectScope": [PID]},
            headers={**_auth(token), "Accept": "text/event-stream"},
        ) as res:
            assert res.status_code == 200, res.read()
            events = _events(res)
        by = {name: data for name, data in events if name != "delta"}
        assert "error" not in by, by.get("error")
        text = "".join(d["text"] for n, d in events if n == "delta")
        summary = {
            "question": question,
            "route": by["start"]["routing"]["type"],
            "measure": by["start"]["routing"]["measureKey"],
            "chunks": by["start"]["retrievedChunkCount"],
            "top": next((s["sourceLabel"] for s in by["sources"]["sources"]), "-"),
            "finish": by["done"]["finishReason"],
            "elapsed_ms": by["done"]["elapsedMs"],
            "infographic": by.get("infographic"),
            "text": text,
        }
        print(
            f"\n| {question} | {summary['route']} | {summary['measure'] or '-'} | "
            f"{summary['chunks']} | {summary['top']} | {summary['finish']} | "
            f"{summary['elapsed_ms'] / 1000:.1f}s |\n  답: {text[:160]!r}"
        )
        return summary

    yield _ask
    with tx() as cur:
        cur.execute("delete from conversation where id = %s", (created["id"],))


@live
@requires_db
def test_문서_질문은_맞는_문서를_1순위로_문다(ask):
    result = ask("GitHub 와 Redmine 의 인증 방식은 어떻게 다른가요?")
    assert result["route"] == "DOCUMENT"
    assert result["top"] == "ARC-003 도구 연동방식"
    assert result["chunks"] >= 1 and result["text"].strip()
    assert "[1]" in result["text"]  # 각주가 붙는다

    # "진척률" 은 카탈로그 지표이기도 해서 모델이 집계 경로를 고르기도 한다. 그래도 문서
    # 근거가 게이트를 넘으면 MIXED 로 같이 실린다. 어느 쪽이든 1순위 근거는 그 문서다.
    result = ask("진척률은 어떻게 산정하나요?")
    assert result["route"] in ("DOCUMENT", "MIXED")
    assert result["top"] == "진척률 산정체계"


@live
@requires_db
def test_관계없는_질문은_게이트에_막힌다(ask):
    result = ask("김치찌개 맛있게 끓이는 법 알려줘")
    assert result["finish"] == "NO_EVIDENCE"
    assert result["chunks"] == 0 and result["top"] == "-"
    assert "근거" in result["text"]


@live
@requires_db
def test_집계_질문은_인포그래픽으로_가고_숫자는_집계_안에_있다(ask):
    result = ask("이슈가 모두 몇 건인가요?")
    assert result["route"] in ("AGGREGATE", "MIXED")
    assert result["measure"] in ("issue_count", "open_issue_count")
    assert result["infographic"] is not None
    assert result["infographic"]["data"]["measure"] == result["measure"]
    # 답의 숫자가 집계 값 밖이면 NUMBER_GUARD 표시가 붙는다. 실모델도 지시를 지켜야 한다.
    assert result["finish"] == "STOP", result["text"]
