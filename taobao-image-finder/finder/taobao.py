"""타오바오 이미지검색(拍立淘) 및 상품 페이지 이미지 추출.

주의: 타오바오는 화면 구조/클래스명을 자주 바꾼다. 그래서 특정 클래스 대신
- 파일 업로드는 페이지의 input[type=file] 을 찾아 넣고
- 결과는 item.taobao.com / detail.tmall.com 링크와 alicdn 이미지 패턴으로 수집한다.
구조가 바뀌어 실패하면 --debug 로 스크린샷/HTML을 저장해 선택자를 조정할 것.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .browser import auto_scroll

TAOBAO_HOME = "https://www.taobao.com/"
_ALICDN_RE = re.compile(
    r"(?:https?:)?//(?:img|gw|g\.search\d?|gd\d)\.alicdn\.com/[^\s\"'<>)\\]+?\.(?:jpe?g|png|webp)",
    re.I,
)
# 결과 썸네일 접미사: xxx.jpg_220x220q90.jpg_.webp → 원본 xxx.jpg
_SUFFIX_RE = re.compile(r"(\.(?:jpe?g|png|webp))(?:_[^/]*)$", re.I)


@dataclass
class TaobaoItem:
    item_id: str
    url: str
    title: str = ""
    price: str = ""
    thumb: str = ""
    images: list[str] = field(default_factory=list)  # 상품 페이지 전체 이미지
    similarity: float | None = None


def original_image(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    url = url.split("?")[0]
    return _SUFFIX_RE.sub(r"\1", url)


def clean_item_url(url: str, item_id: str) -> str:
    host = "detail.tmall.com" if "tmall.com" in url else "item.taobao.com"
    return f"https://{host}/item.htm?id={item_id}"


def item_id_from_url(url: str) -> str:
    q = parse_qs(urlparse(url if "://" in url else "https:" + url).query)
    return (q.get("id") or [""])[0]


def image_search(ctx, image_path: Path, limit: int = 20, debug_dir: Path | None = None) -> list[TaobaoItem]:
    """대표 이미지로 타오바오 이미지검색 → 상위 결과 상품 목록."""
    page = ctx.new_page()
    page.goto(TAOBAO_HOME, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)

    if "login" in page.url:
        raise RuntimeError("타오바오 로그인이 필요합니다. 먼저 `python -m finder login` 을 실행하세요.")

    # 카메라(이미지검색) 아이콘 클릭 시도 → input[type=file] 노출
    for sel in [
        "[class*='image-search']", "[class*='imgsearch']", "[class*='camera']",
        "[aria-label*='图']", "[title*='图片搜索']", "[class*='drop-wrapper']",
    ]:
        el = page.query_selector(sel)
        if el and el.is_visible():
            try:
                el.click(timeout=2000)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

    inputs = page.query_selector_all("input[type=file]")
    if not inputs:
        _dump(page, debug_dir, "no_file_input")
        raise RuntimeError("이미지검색 업로드 입력창을 찾지 못했습니다(타오바오 화면 변경 가능). --debug 결과를 확인하세요.")

    with ctx.expect_page(timeout=15000) as new_page_info:
        try:
            inputs[0].set_input_files(str(image_path))
        except Exception:
            pass
    try:
        res = new_page_info.value
    except Exception:
        res = page  # 같은 탭에서 결과로 이동하는 경우
    res.wait_for_load_state("domcontentloaded", timeout=60000)
    res.wait_for_timeout(4000)
    auto_scroll(res, steps=6)
    _dump(res, debug_dir, "search_result")

    items = res.evaluate(
        """() => {
          const out = [], seen = new Set();
          for (const a of document.querySelectorAll('a[href]')) {
            const h = a.href;
            if (!/(item\\.taobao\\.com\\/item\\.htm|detail\\.tmall\\.com\\/item\\.htm)/.test(h)) continue;
            const m = h.match(/[?&]id=(\\d+)/); if (!m || seen.has(m[1])) continue;
            seen.add(m[1]);
            const img = a.querySelector('img');
            const txt = (a.innerText || '').trim().split('\\n');
            const price = (a.innerText.match(/[¥￥]\\s?([\\d.]+)/) || [,''])[1];
            out.push({id: m[1], url: h, thumb: img ? (img.currentSrc || img.src || img.dataset.src || '') : '',
                      title: (img && img.alt) || txt[0] || '', price});
          }
          return out;
        }"""
    )
    results = [
        TaobaoItem(item_id=i["id"], url=clean_item_url(i["url"], i["id"]),
                   title=i["title"][:120], price=i["price"],
                   thumb=original_image(i["thumb"]) if i["thumb"] else "")
        for i in items
    ]
    if res is not page:
        res.close()
    page.close()
    return results[:limit]


def item_images(ctx, item: TaobaoItem, debug_dir: Path | None = None) -> list[str]:
    """상품 상세 페이지의 대표/SKU/상세설명 이미지 전체 수집."""
    page = ctx.new_page()
    try:
        page.goto(item.url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        auto_scroll(page, steps=30)
        html = page.content()
        dom_srcs = page.evaluate(
            "() => Array.from(document.images).map(i => i.currentSrc || i.src || i.dataset.src || '')"
        )
        _dump(page, debug_dir, f"item_{item.item_id}")
    finally:
        page.close()

    urls = [m.group(0) for m in _ALICDN_RE.finditer(html.replace("\\/", "/"))] + list(dom_srcs)
    out, seen = [], set()
    for u in urls:
        if not u or "alicdn.com" not in u:
            continue
        u = original_image(u)
        if re.search(r"(tps-\d+-\d+|/tfs/|sprite|icon|logo|avatar)", u, re.I):
            continue  # UI 아이콘류 제외
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _dump(page, debug_dir: Path | None, name: str):
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(debug_dir / f"{name}.png"), full_page=False)
        (debug_dir / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
