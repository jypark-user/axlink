"""시나리오의 화면 확인 단계.

API 로 상태를 단언한 시나리오가 같은 상태를 실제 브라우저 화면에서도 확인한다. 원격 대상
(`AXLINK_TARGET_URL`, 웹과 API 를 같은 주소로 내는 서버)에 `AXLINK_BROWSER_CHROME`(설치된
Chrome·Edge 실행 파일)이 있을 때만 돈다. 없으면 `ui` 픽스처가 None 이고 시나리오는 API 단언만 한다.

화면 단계를 끝까지 돈 시험은 junit 속성 `proves=browser` 를 남긴다. `record-junit` 이 그
시험의 실행 기록에만 browser 증거를 더한다. 화면 사진은 `AXLINK_BROWSER_OUT`(기본
`var/verify/evidence/browser`) 아래 시험 이름 폴더에 남는다.

로그인은 화면의 로그인 양식으로 한다. 계정마다 한 번 로그인하고 같은 모듈 안에서는 그 브라우저
문맥을 다시 쓴다(로그인 횟수를 줄인다).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

CHROME = os.environ.get("AXLINK_BROWSER_CHROME")
OUT = Path(os.environ.get("AXLINK_BROWSER_OUT", "var/verify/evidence/browser"))


class Screen:
    """한 계정으로 로그인한 브라우저 탭. 시험 하나 동안 쓴다."""

    def __init__(self, ui: UI, page: Any, test: str) -> None:
        self.ui = ui
        self.page = page
        self.test = test
        self.record_property: Any = lambda *_: None
        self.console: list[str] = []
        self.failed: list[str] = []
        self.denied: list[str] = []  # 서버가 거절한 응답(403·404)
        self.allow_denied = False
        page.on("console", lambda m: m.type == "error" and self.console.append(m.text))
        page.on("pageerror", lambda e: self.console.append(str(e)))
        page.on("response", self._response)

    def _response(self, r: Any) -> None:
        if r.status >= 500:
            self.failed.append(f"{r.status} {r.url}")
        elif r.status in (403, 404) and "/api/" in r.url:
            self.denied.append(f"{r.status} {r.url}")

    def expect_denied(self) -> Screen:
        """거절을 기대하는 화면. 서버의 403·404 가 콘솔에 남는 것을 오류로 보지 않는다."""
        self.allow_denied = True
        return self

    def open(self, path: str) -> Screen:
        self.page.goto(self.ui.base + path, wait_until="networkidle")
        return self

    def shot(self, name: str) -> Path:
        folder = OUT / self.test
        folder.mkdir(parents=True, exist_ok=True)
        # 한 시험 안에서 계정을 바꿔 화면을 여럿 열어도 번호가 이어지게 폴더의 파일 수로 센다
        n = len(list(folder.glob("*.png"))) + 1
        p = folder / f"{n:02d}-{name}.png"
        self.page.screenshot(path=str(p), full_page=True)
        if name == "실패":
            p.with_suffix(".txt").write_text(self.text("body"), encoding="utf-8")
        return p

    def text(self, selector: str = "main") -> str:
        loc = self.page.locator(selector)
        if loc.count() == 0:
            loc = self.page.locator("body")
        return loc.first.inner_text()

    def see(self, *texts: str | re.Pattern[str], selector: str = "main", timeout: int = 15000):
        """화면에 글자가 모두 보일 때까지 기다린다. 못 보면 화면 사진을 남기고 실패한다."""
        from playwright.sync_api import expect

        scope = self.page.locator(selector).first if self.page.locator(selector).count() else (
            self.page.locator("body")
        )
        for t in texts:
            try:
                expect(scope).to_contain_text(t, timeout=timeout)
            except AssertionError:
                self.shot("실패")
                raise
        return self

    def not_see(self, *texts: str | re.Pattern[str], selector: str = "main") -> Screen:
        body = self.text(selector)
        for t in texts:
            found = bool(t.search(body)) if isinstance(t, re.Pattern) else t in body
            if found:
                self.shot("실패")
                raise AssertionError(f"화면에 보이면 안 되는 글자가 보인다: {t!r}")
        return self

    def row(self, contains: str) -> str:
        """그 글자가 든 표 줄의 글자."""
        loc = self.page.locator("tr", has_text=contains)
        if loc.count() == 0:
            self.shot("실패")
            raise AssertionError(f"표에 {contains!r} 줄이 없다")
        return loc.first.inner_text()

    def done(self) -> None:
        """화면 단계 끝. 콘솔 오류·서버 오류가 없어야 한다. browser 증거를 남긴다."""
        self.shot("끝")
        self.page.close()
        assert not self.failed, f"서버 오류 응답: {self.failed[:5]}"
        console = self.console
        if self.allow_denied:
            console = [c for c in console if not re.search(r"status of (403|404)", c)]
        assert not console, f"콘솔 오류: {console[:5]}"
        self.record_property("proves", "browser")
        self.record_property("screenshots", (OUT / self.test).as_posix())


class UI:
    def __init__(self, base: str, browser: Any, password: str) -> None:
        self.base = base.rstrip("/")
        self.browser = browser
        self.password = password
        self.contexts: dict[str, Any] = {}

    def _context(self, username: str) -> Any:
        ctx = self.contexts.get(username)
        if ctx is not None:
            return ctx
        ctx = self.browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="ko-KR", timezone_id="Asia/Seoul"
        )
        page = ctx.new_page()
        page.goto(self.base + "/login", wait_until="networkidle")
        page.fill("#username", username)
        page.fill("#password", self.password)
        page.click("button[type=submit]")
        page.wait_for_url(lambda u: "/login" not in u, timeout=40000)
        page.close()
        self.contexts[username] = ctx
        return ctx

    def screen(self, username: str, test: str) -> Screen:
        return Screen(self, self._context(username).new_page(), test)

    def close(self) -> None:
        for ctx in self.contexts.values():
            ctx.close()
        self.contexts.clear()


def open_ui(base: str | None, password: str) -> Iterator[UI | None]:
    if not (base and CHROME):
        yield None
        return
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)
        ui = UI(base, browser, password)
        try:
            yield ui
        finally:
            ui.close()
            browser.close()
