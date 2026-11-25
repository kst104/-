"""이미지 다운로드, 중복 제거, 유사도(지각 해시) 계산, 결과 갤러리 HTML 생성."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import requests

from .browser import UA

HEADERS_BY_HOST = {
    "coupangcdn.com": {"Referer": "https://www.coupang.com/"},
    "alicdn.com": {"Referer": "https://www.taobao.com/"},
}


def _headers(url: str) -> dict:
    h = {"User-Agent": UA}
    for host, extra in HEADERS_BY_HOST.items():
        if host in url:
            h.update(extra)
    return h


def download_all(urls: list[str], out_dir: Path, prefix: str = "") -> list[Path]:
    """URL 목록을 내려받아 out_dir에 저장. 내용이 같은 파일은 1개만 남긴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved, digests = [], set()
    s = requests.Session()
    for n, url in enumerate(urls, 1):
        try:
            r = s.get(url, headers=_headers(url), timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"   ! 실패 {url} ({e})")
            continue
        data = r.content
        if len(data) < 2048:  # 1x1 픽셀/아이콘
            continue
        d = hashlib.md5(data).hexdigest()
        if d in digests:
            continue
        digests.add(d)
        ext = _ext(r.headers.get("Content-Type", ""), url)
        p = out_dir / f"{prefix}{n:03d}{ext}"
        p.write_bytes(data)
        saved.append(p)
    return saved


def _ext(ctype: str, url: str) -> str:
    for k, e in (("webp", ".webp"), ("png", ".png"), ("gif", ".gif"), ("jpeg", ".jpg"), ("jpg", ".jpg")):
        if k in ctype or url.lower().endswith(e):
            return e
    return ".jpg"


def similarity(a: Path, b: Path) -> float | None:
    """지각 해시(pHash) 기반 0~1 유사도. imagehash 미설치 시 None."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None
    try:
        ha = imagehash.phash(Image.open(a).convert("RGB"))
        hb = imagehash.phash(Image.open(b).convert("RGB"))
    except Exception:
        return None
    return round(1 - (ha - hb) / 64, 3)


def write_report(out_root: Path, report: dict):
    (out_root / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def imgs(paths):
        return "".join(
            f'<a href="{html.escape(p)}" target="_blank"><img loading="lazy" src="{html.escape(p)}"></a>'
            for p in paths
        )

    c = report["coupang"]
    parts = [
        "<!doctype html><meta charset=utf-8><title>이미지 추출 결과</title>",
        "<style>body{font-family:sans-serif;margin:16px;background:#fafafa}"
        "img{height:140px;margin:3px;border:1px solid #ddd;background:#fff}"
        "section{background:#fff;padding:12px;margin:12px 0;border-radius:8px}"
        "h2{font-size:16px}.m{color:#666;font-size:13px}</style>",
        f"<h1>{html.escape(c.get('title') or c['product_id'])}</h1>",
        f'<p class=m>쿠팡: <a href="{html.escape(c["url"])}">{html.escape(c["url"])}</a></p>',
        "<section><h2>쿠팡 이미지</h2>", imgs(c.get("files", [])), "</section>",
    ]
    for it in report.get("taobao", []):
        sim = f" · 유사도 {it['similarity']:.2f}" if it.get("similarity") is not None else ""
        parts += [
            "<section>",
            f'<h2><a href="{html.escape(it["url"])}" target=_blank>{html.escape(it.get("title") or it["item_id"])}</a></h2>',
            f'<p class=m>¥{html.escape(it.get("price") or "-")}{sim} · 이미지 {len(it.get("files", []))}장</p>',
            imgs(it.get("files", [])), "</section>",
        ]
    (out_root / "index.html").write_text("".join(parts), encoding="utf-8")
