"""쿠팡 상품 입력 파싱 + 상품 페이지에서 이미지 URL 추출."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, parse_qs

PRODUCT_URL = "https://www.coupang.com/vp/products/{pid}"

# 쿠팡 이미지 CDN: thumbnail*.coupangcdn.com, image*.coupangcdn.com
_CDN_RE = re.compile(r"https?://[a-z0-9.-]*coupangcdn\.com/[^\s\"'<>)]+", re.I)
_IMG_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)(\?|$)", re.I)
# 썸네일 리사이즈 구간: /thumbnails/remote/492x492ex/  → 큰 사이즈로 치환
_RESIZE_RE = re.compile(r"/thumbnails/remote/\d+x\d+[a-z]*/", re.I)


@dataclass
class CoupangProduct:
    product_id: str
    url: str
    title: str = ""
    seller: str = ""  # 판매자명(가능할 때만, 화면 구조에 따라 빈 값)
    main_images: list[str] = field(default_factory=list)    # 대표/갤러리
    detail_images: list[str] = field(default_factory=list)  # 상세페이지


def parse_input(text: str) -> tuple[str, str]:
    """상품번호 또는 링크 → (product_id, 정규화된 URL).

    지원: '7335597976', 'https://www.coupang.com/vp/products/7335597976?itemId=..',
    'https://m.coupang.com/vm/products/7335597976', 'coupang.com/vp/products/...'.
    공유용 단축링크(link.coupang.com/a/...)는 리다이렉트를 따라가야 하므로
    브라우저 단계에서 처리한다(product_id='' 반환).
    """
    text = text.strip()
    if re.fullmatch(r"\d{5,}", text):
        return text, PRODUCT_URL.format(pid=text)
    if not re.match(r"https?://", text):
        text = "https://" + text
    u = urlparse(text)
    m = re.search(r"/(?:vp|vm)/products/(\d+)", u.path)
    if m:
        pid = m.group(1)
        q = parse_qs(u.query)
        url = PRODUCT_URL.format(pid=pid)
        keep = [f"{k}={q[k][0]}" for k in ("itemId", "vendorItemId") if k in q]
        if keep:
            url += "?" + "&".join(keep)
        return pid, url
    if "coupang" in u.netloc:
        return "", text  # 단축링크 등: 브라우저로 열어 최종 URL에서 다시 파싱
    raise ValueError(f"쿠팡 상품번호/링크로 인식할 수 없습니다: {text}")


def upscale(url: str, size: int = 1000) -> str:
    """썸네일 URL의 리사이즈 구간을 큰 사이즈로 바꾼다(원본보다 크게 요청해도 원본 크기로 응답)."""
    url = url.split("?")[0]
    if url.startswith("//"):
        url = "https:" + url
    return _RESIZE_RE.sub(f"/thumbnails/remote/{size}x{size}ex/", url)


def _norm(u: str, base: str) -> str | None:
    if not u or u.startswith("data:"):
        return None
    u = u.strip()
    if u.startswith("//"):
        u = "https:" + u
    u = urljoin(base, u)
    if "coupangcdn.com" not in u:
        return None
    if not _IMG_EXT_RE.search(u):
        return None
    # 아이콘/뱃지/로고류 제외
    if re.search(r"(icon|badge|logo|sprite|rocket|delivery|/np/)", u, re.I):
        return None
    return u


def _dedupe(urls):
    seen, out = set(), []
    for u in urls:
        key = _RESIZE_RE.sub("/", u.split("?")[0])
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def extract_seller(html: str) -> str:
    """판매자명 추출(최선 노력). 쿠팡 화면 구조가 바뀌면 빈 문자열."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for sel in [".prod-sale-vendor-name", "a.prod-sale-vendor-name", "[class*='vendor-name']",
                "[class*='seller-name']", "[class*='SellerName']"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    m = re.search(r'"vendorName"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r"판매자\s*[:：]?\s*</?[^>]*>\s*([^<]{2,40})<", html)
    return m.group(1).strip() if m else ""


def extract_from_html(html: str, base_url: str) -> tuple[str, list[str], list[str]]:
    """상품 HTML에서 (제목, 대표이미지들, 상세이미지들) 추출.

    쿠팡은 클래스명을 자주 바꾸므로 특정 선택자에 의존하지 않고
    og:image / JSON-LD / 이미지 CDN 패턴으로 넓게 수집한다.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og_t = soup.find("meta", property="og:title")
    if og_t and og_t.get("content"):
        title = og_t["content"].strip()
    elif soup.title:
        title = soup.title.get_text(strip=True)
    title = re.sub(r"\s*[-|]\s*쿠팡!?\s*$", "", title)

    main: list[str] = []
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        main.append(og["content"])

    # JSON-LD Product.image
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "Product":
                imgs = d.get("image") or []
                main.extend([imgs] if isinstance(imgs, str) else imgs)
                if not title and d.get("name"):
                    title = d["name"]

    detail: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("data-img-src") or img.get("src") or ""
        u = _norm(src, base_url)
        if not u:
            continue
        # 상세페이지 영역(vendor_inventory 등) 이미지는 detail로
        in_detail = any(
            p.get("id") in ("productDetail", "btfTab") or
            any("detail" in c.lower() for c in (p.get("class") or []))
            for p in img.parents if hasattr(p, "get")
        )
        (detail if in_detail or "/vendor_inventory/" in u else main).append(u)

    # 스크립트/스타일 속 CDN URL도 보조 수집 (갤러리 JSON 등)
    for m in _CDN_RE.finditer(html.replace("\\/", "/")):
        u = _norm(m.group(0), base_url)
        if u and "/thumbnails/" in u and "/vendor_inventory/" not in u:
            main.append(u)

    main = _dedupe([upscale(u) for u in (_norm(x, base_url) or "" for x in main) if u])
    detail = _dedupe([u.split("?")[0] for u in detail])
    detail = [u for u in detail if u not in main]
    return title, main, detail
