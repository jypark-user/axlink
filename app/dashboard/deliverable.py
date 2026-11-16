"""WBS 항목의 산출물 제출 판정 (ARC-016 2단계). 순수 함수만 둔다.

WBS 산출물 열은 업체마다 꼴이 다르다. 저장소 경로, 파일 이름, 산출물 유형 이름 순으로
본다. 하나라도 맞으면 제출이다. 맞는 게 없으면 미제출이고, 종료일이 오늘보다 앞이면
지연이다. 판정마다 어느 규칙이 어느 파일과 맞았는지 남긴다. 발주기관이 "왜 제출로 보나" 를
물었을 때 답이 있어야 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from app.standard.work_product_type import DISPLAY_NAMES

NONE = "NONE"
SUBMITTED = "SUBMITTED"
MISSING = "MISSING"
OVERDUE = "OVERDUE"

RULE_LINK = "LINKED_DOC"
RULE_PATH = "REPO_PATH"
RULE_NAME = "FILE_NAME"
RULE_TYPE = "PRODUCT_TYPE"
RULE_DESIGNATED = "DESIGNATED"  # 발주기관 지정 항목으로 판정(UC-033)

_PATH_LIKE = re.compile(r"[\\/]|\.[A-Za-z0-9]{1,5}$")


@dataclass(frozen=True)
class RepoTree:
    """수집한 저장소 파일 목록. 한 번의 트리 조회 결과다."""

    sha: str
    paths: frozenset[str]
    blob_url_base: str | None  # https://github.com/o/r/blob/<sha>/  꼴. 없으면 링크를 못 만든다

    def url_for(self, path: str) -> str | None:
        return f"{self.blob_url_base}{path}" if self.blob_url_base else None


@dataclass(frozen=True)
class Judgement:
    wbs_id: str
    status: str
    rule: str | None = None
    ref: str | None = None
    url: str | None = None
    # 맞춘 근거가 산출물 항목이면 그 id. 저장소 파일만 맞았으면 None 이다(제출 여부를 모른다)
    product_id: str | None = None


def _id(value: Any) -> str | None:
    return str(value) if value else None


def _norm_path(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./").casefold()


def _stem(value: str) -> str:
    """경로·확장자를 뗀 이름. 공백은 하나로 모은다."""
    name = PurePosixPath(value.strip().replace("\\", "/")).name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return " ".join(stem.split()).casefold()


def stem_of(value: str) -> str:
    """바깥에서 같은 이름 규칙으로 문서를 항목에 붙일 때 쓴다."""
    return _stem(value)


def _type_by_name() -> dict[str, str]:
    return {" ".join(label.split()).casefold(): code for code, label in DISPLAY_NAMES.items()}


def judge(
    items: list[dict[str, Any]],
    *,
    tree: RepoTree | None,
    products: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    today: date,
    designated: dict[str, Any] | None = None,
) -> list[Judgement]:
    """말단 항목마다 판정 하나. 묶음(weight 없음)과 산출물 열이 빈 항목은 NONE.

    products: 현행 산출물 행. type · title · status · file_uri · external_url · id
    documents: 올린 문서. id · original_filename
    designated: 작업 정체(task_key) → 발주기관 지정 항목 현황(total · submitted). 지정이 있는
        작업은 산출물 열 대신 「지정 항목이 모두 제출됐는가」로 판정한다(UC-033 4단계).
    """
    designated = designated or {}
    product_paths = {
        _norm_path(p["file_uri"]): p for p in products if p.get("file_uri")
    }
    product_titles = {_stem(p["title"]): p for p in products if p.get("title")}
    product_by_type = {p["type"]: p for p in products if p.get("type")}
    doc_names = {_stem(d["original_filename"]): d for d in documents if d.get("original_filename")}
    linked: dict[str, dict] = {}
    for d in documents:  # 최근 것이 앞에 온다. 항목마다 첫 것만 근거로 쓴다
        key = str(d["wbs_item_id"]) if d.get("wbs_item_id") else None
        if key and key not in linked:
            linked[key] = d
    type_names = _type_by_name()

    out: list[Judgement] = []
    for item in items:
        wbs_id = item["wbs_id"]
        deliverable = (item.get("deliverable") or "").strip()
        cover = designated.get(str(item.get("task_key"))) if item.get("task_key") else None
        if item.get("weight") is not None and cover is not None and cover.total > 0:
            ref = f"지정 산출물 {cover.total}건 중 {cover.submitted}건 제출"
            if cover.submitted >= cover.total:
                out.append(Judgement(wbs_id, SUBMITTED, RULE_DESIGNATED, ref))
            else:
                end = item.get("end_on")
                late = end is not None and end < today
                out.append(Judgement(wbs_id, OVERDUE if late else MISSING, RULE_DESIGNATED, ref))
            continue
        if item.get("weight") is None or not deliverable:
            out.append(Judgement(wbs_id, NONE))
            continue

        doc = linked.get(str(item.get("id"))) if item.get("id") else None
        if doc is not None:
            # 0) 항목에 직접 올린 문서. 이름이 달라도 그 항목의 산출물이다
            out.append(Judgement(
                wbs_id, SUBMITTED, RULE_LINK, doc["original_filename"],
                f"/api/documents/{doc['id']}/content", _id(doc.get("work_product_id")),
            ))
            continue
        found = _match(deliverable, tree, product_paths, product_titles, product_by_type,
                       doc_names, type_names)
        if found is not None:
            out.append(Judgement(wbs_id, SUBMITTED, *found))
            continue

        end = item.get("end_on")
        status = OVERDUE if end is not None and end < today else MISSING
        out.append(Judgement(wbs_id, status))
    return out


def _match(
    deliverable: str,
    tree: RepoTree | None,
    product_paths: dict[str, dict],
    product_titles: dict[str, dict],
    product_by_type: dict[str, dict],
    doc_names: dict[str, dict],
    type_names: dict[str, str],
) -> tuple[str, str, str | None, str | None] | None:
    # 1) 저장소 경로. 경로 꼴일 때만 본다
    if _PATH_LIKE.search(deliverable):
        norm = _norm_path(deliverable)
        if tree is not None:
            hit = next((p for p in tree.paths if p.casefold() == norm), None)
            if hit is not None:
                return RULE_PATH, hit, tree.url_for(hit), None
            # 폴더를 적은 경우. 그 아래 파일이 하나라도 있으면 있는 것이다
            folder = norm.rstrip("/") + "/"
            inside = sorted(p for p in tree.paths if p.casefold().startswith(folder))
            if inside:
                shown = deliverable.strip().replace("\\", "/").rstrip("/")
                return (
                    RULE_PATH, f"{shown}/ ({len(inside)}개 파일)", tree.url_for(inside[0]), None
                )
        product = product_paths.get(norm)
        if product is not None:
            return RULE_PATH, product["file_uri"], product.get("external_url"), _id(product["id"])

    # 2) 파일 이름. 올린 문서나 산출물 제목과 같으면
    stem = _stem(deliverable)
    if stem:
        doc = doc_names.get(stem)
        if doc is not None:
            return (
                RULE_NAME, doc["original_filename"], f"/api/documents/{doc['id']}/content",
                _id(doc.get("work_product_id")),
            )
        product = product_titles.get(stem)
        if product is not None and product.get("status") not in (None, "NONE"):
            return RULE_NAME, product["title"], product.get("external_url"), _id(product["id"])

    # 3) 산출물 유형 이름. "사업수행계획서" 처럼 22종 이름이면 그 유형의 현행 산출물
    code = type_names.get(" ".join(deliverable.split()).casefold())
    if code is not None:
        product = product_by_type.get(code)
        if product is not None and product.get("status") not in (None, "NONE"):
            return RULE_TYPE, DISPLAY_NAMES[code], product.get("external_url"), _id(product["id"])
    return None


def summarize(judgements: list[Judgement]) -> dict[str, int]:
    counts = {SUBMITTED: 0, MISSING: 0, OVERDUE: 0, NONE: 0}
    for j in judgements:
        counts[j.status] = counts.get(j.status, 0) + 1
    return counts
