"""Playwright 브라우저(영구 프로필) 관리.

쿠팡(Akamai 봇차단)과 타오바오(로그인 필수)는 일반 requests로는 막히므로
실제 Chromium을 띄우고, 한번 로그인한 세션을 profile 폴더에 저장해 재사용한다.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

DEFAULT_PROFILE = Path.home() / ".taobao-image-finder" / "profile"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@contextlib.contextmanager
def open_context(profile: Path = DEFAULT_PROFILE, headless: bool = False, cdp: str | None = None):
    """cdp 를 주면 이미 실행 중인 Chromium 계열 브라우저(원격 디버깅 포트)에 붙는다.
    예: 브라우저를 --remote-debugging-port=9222 로 실행 후 cdp="http://localhost:9222".
    이때는 그 브라우저의 로그인 상태를 그대로 쓰고, 끝나도 브라우저를 닫지 않는다."""
    from playwright.sync_api import sync_playwright

    if cdp:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            yield ctx
        return

    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            user_agent=UA,
            locale="ko-KR",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        try:
            yield ctx
        finally:
            ctx.close()


def auto_scroll(page, steps: int = 25, pause_ms: int = 400):
    """지연로딩(lazy) 이미지를 불러오기 위해 끝까지 스크롤."""
    for _ in range(steps):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(pause_ms)
        at_bottom = page.evaluate(
            "window.innerHeight + window.scrollY >= document.body.scrollHeight - 50"
        )
        if at_bottom:
            break
