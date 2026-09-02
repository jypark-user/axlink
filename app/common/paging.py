"""페이지 응답. 프런트 types/api.ts 의 PageResponse<T> 와 필드가 일치해야 한다."""

from typing import Any

from pydantic import BaseModel


class PageQuery(BaseModel):
    page: int = 0
    size: int = 20
    sort: str | None = None

    @property
    def offset(self) -> int:
        return self.page * self.size


class PageResponse[T](BaseModel):
    content: list[T]
    page: int
    size: int
    totalElements: int  # noqa: N815 — 프런트 계약 필드명이다
    totalPages: int  # noqa: N815
    hasNext: bool  # noqa: N815

    @staticmethod
    def of(content: list[Any], query: PageQuery, total: int) -> "PageResponse[Any]":
        size = max(query.size, 1)
        total_pages = (total + size - 1) // size
        return PageResponse(
            content=content,
            page=query.page,
            size=query.size,
            totalElements=total,
            totalPages=total_pages,
            hasNext=(query.page + 1) < total_pages,
        )
