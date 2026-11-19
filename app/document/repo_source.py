"""저장소 파일을 산출물로 올리기(11-19 사용자 결정).

저장소에 커밋한 산출물도 자동으로 제출로 보지 않는다. 용역사가 올리기에서 저장소 파일을 골라야
제출이다. 고른 파일은 수집한 트리에 있는 것만 받고, 그 커밋 시점 본문을 도구에서 받아 올린
문서와 똑같이 남긴다. 그래야 승인 단위(올라온 산출물)와 원문 보기·내려받기가 하나로 맞는다.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.auth.models import AuthPrincipal
from app.common import crypto, errors
from app.document import extractor
from app.document.access import require_project
from app.integration import port
from app.integration import repository as integration_repo


@dataclass(frozen=True)
class RepoSource:
    tool: str
    base_url: str
    target: str
    token: str
    ref: str | None
    path: str


def _supported(path: str) -> bool:
    return extractor.ext_of(path) in extractor.SUPPORTED_EXTS


def list_paths(cur: Any, principal: AuthPrincipal, project_id: str) -> list[str]:
    """올릴 수 있는 저장소 파일 경로(가장 최근 수집한 트리, 문서 형식만)."""
    require_project(cur, principal, project_id)
    row = integration_repo.github_tree_source(cur, project_id)
    if row is None:
        return []
    paths = (row["payload"] or {}).get("paths") or []
    return sorted(p for p in paths if isinstance(p, str) and _supported(p))


def prepare(cur: Any, principal: AuthPrincipal, project_id: str, path: str) -> RepoSource:
    """받을 준비. 트리에 없는 경로는 받지 않는다(임의 경로로 도구를 부르지 않게)."""
    require_project(cur, principal, project_id)
    path = (path or "").strip()
    row = integration_repo.github_tree_source(cur, project_id)
    payload = (row or {}).get("payload") or {}
    if row is None or path not in (payload.get("paths") or []):
        raise errors.validation_failed(f"저장소에 없는 파일입니다: {path}")
    if not _supported(path):
        supported = " · ".join(extractor.SUPPORTED_EXTS)
        raise errors.validation_failed(f"{supported} 만 올릴 수 있습니다.")
    return RepoSource(
        tool=row["tool"], base_url=row["base_url"], target=row["target_resource"],
        token=crypto.decrypt(row["auth_encrypted"]),
        ref=payload.get("commit") or payload.get("sha") or None, path=path,
    )


def fetch(src: RepoSource) -> tuple[str, bytes]:
    """도구에서 본문을 받는다. 트랜잭션 밖에서 부른다(외부 호출 동안 DB 를 잡지 않게)."""
    got = port.get_connector(src.tool).fetch_file(
        src.base_url, src.target, src.token, src.path, src.ref
    )
    if got is None:
        raise errors.not_found("저장소 파일", src.path)
    try:
        content = base64.b64decode(got.get("content") or "")
    except ValueError as exc:
        raise errors.ApiError(502, "TOOL_BAD_RESPONSE", "파일 본문을 읽지 못했습니다.") from exc
    return PurePosixPath(src.path).name, content
