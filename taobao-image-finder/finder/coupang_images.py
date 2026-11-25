"""API 키 없이 쿠팡 상품 페이지를 열어 대표·상세 이미지를 내려받는다 (타오바오 검색 없음).

사용:
  python -m finder.coupang_images https://www.coupang.com/vp/products/7335597976
  python -m finder.coupang_images 7335597976 8123456789 --out ~/Downloads/coupang
  python -m finder.coupang_images --file links.txt          # 한 줄에 링크/번호 하나
옵션: --no-detail(대표만) --debug(스크린샷·HTML 저장) --headless(창 숨김, 차단 위험↑)

결과: <out>/coupang_<번호>/main_001.jpg…, detail_001.jpg…, info.json, index.html
  info.json 에 상품 URL, 상품명, 판매자(가능할 때), 각 파일의 원본 이미지 URL이 기록된다.
"""
from __future__ import annotations

import argparse
import html as H
import json
import sys
import time
from pathlib import Path

from .__main__ import fetch_coupang
from .browser import DEFAULT_PROFILE, open_context
from .download import download_all


def save_product(cp, out_root: Path, with_detail: bool) -> Path:
    root = out_root / f"coupang_{cp.product_id}"
    files = []
    for kind, urls in (("main", cp.main_images), ("detail", cp.detail_images if with_detail else [])):
        for n, url in enumerate(urls, 1):
            saved = download_all([url], root, "tmp_")
            if saved:
                dst = saved[0].with_name(f"{kind}_{n:03d}{saved[0].suffix}")
                saved[0].replace(dst)
                files.append({"type": kind, "file": dst.name, "source_url": url})
    info = {"product_id": cp.product_id, "product_url": cp.url, "title": cp.title,
            "seller": cp.seller, "images": files}
    (root / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    cells = "".join(
        f'<figure><a href="{H.escape(f["file"])}" target=_blank><img loading=lazy src="{H.escape(f["file"])}"></a>'
        f'<figcaption>{f["type"]} · {H.escape(f["file"])}</figcaption></figure>' for f in files)
    (root / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>쿠팡 이미지</title>"
        "<style>body{font-family:sans-serif;margin:16px}figure{display:inline-block;margin:4px}"
        "img{height:160px;border:1px solid #ddd}figcaption{font-size:11px;color:#666}</style>"
        f"<h1>{H.escape(cp.title or cp.product_id)}</h1>"
        f'<p>판매자: {H.escape(cp.seller or "(확인 안 됨)")} · <a href="{H.escape(cp.url)}">{H.escape(cp.url)}</a></p>'
        + cells, encoding="utf-8")
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(prog="finder.coupang_images", description="쿠팡 상품 이미지 다운로드 (API 키 불필요)")
    ap.add_argument("targets", nargs="*", help="쿠팡 상품 링크 또는 번호 (여러 개 가능)")
    ap.add_argument("--file", help="링크/번호 목록 파일 (한 줄에 하나)")
    ap.add_argument("--out", default="output")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--no-detail", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--cdp", help="이미 켜둔 브라우저에 연결 (예: http://localhost:9222)")
    args = ap.parse_args(argv)

    targets = list(args.targets)
    if args.file:
        targets += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.startswith("#")]
    if not targets:
        ap.error("쿠팡 링크/번호를 하나 이상 주세요.")

    out_root = Path(args.out).expanduser()
    failed = []
    with open_context(Path(args.profile), headless=args.headless, cdp=args.cdp) as ctx:
        for i, t in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] {t}")
            try:
                cp = fetch_coupang(ctx, t, out_root / "_debug" if args.debug else None)
                if not cp.main_images:
                    raise RuntimeError("이미지를 찾지 못함 (--debug 로 페이지 저장 후 확인)")
                root = save_product(cp, out_root, not args.no_detail)
                n = len(json.loads((root / "info.json").read_text(encoding="utf-8"))["images"])
                print(f"   {cp.title or '(제목 없음)'} — {n}장 → {root}")
            except Exception as e:
                print(f"   ! 실패: {e}")
                failed.append(t)
            if i < len(targets):
                time.sleep(3)  # 연속 요청 간격
    if failed:
        sys.exit(f"\n실패 {len(failed)}건: {', '.join(failed)}")


if __name__ == "__main__":
    main()
