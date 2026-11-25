"""사용법
  python -m finder login                       # 최초 1회: 타오바오(+쿠팡) 로그인 세션 저장
  python -m finder <쿠팡링크|상품번호> [옵션]      # 검색 + 이미지 추출

옵션
  --top N        타오바오 결과 중 상세 이미지까지 받을 상품 수 (기본 5)
  --out DIR      저장 폴더 (기본 ./output)
  --no-detail    타오바오 상품 상세 페이지는 열지 않고 검색결과 썸네일만 저장
  --min-sim X    유사도(0~1) X 미만인 결과는 제외 (imagehash 설치 시)
  --debug        각 단계 스크린샷/HTML 저장 (화면 구조 변경 시 원인 파악용)
  --headless     브라우저 창 숨김 (차단 확률이 올라감, 비권장)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import coupang, taobao
from .browser import DEFAULT_PROFILE, auto_scroll, open_context
from .download import download_all, similarity, write_report


def cmd_login(profile: Path):
    with open_context(profile, headless=False) as ctx:
        page = ctx.new_page()
        page.goto("https://login.taobao.com/")
        print("열린 브라우저에서 타오바오에 로그인하세요(QR/계정).")
        print("쿠팡이 차단 화면을 띄우면 쿠팡 탭도 한 번 열어 통과시켜 두세요.")
        ctx.new_page().goto("https://www.coupang.com/")
        input("로그인을 마쳤으면 여기서 Enter ▶ ")
    print(f"세션 저장 완료: {profile}")


def fetch_coupang(ctx, text: str, debug: Path | None) -> coupang.CoupangProduct:
    pid, url = coupang.parse_input(text)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    if not pid:  # 단축링크 → 최종 URL에서 다시 파싱
        pid, url = coupang.parse_input(page.url)
    if "Access Denied" in (page.title() or "") or "denied" in page.content()[:3000].lower():
        input("쿠팡이 접속을 차단했습니다. 브라우저에서 페이지가 보이게 한 뒤 Enter ▶ ")
    auto_scroll(page, steps=30)  # 상세 이미지 지연로딩
    # '상세정보 펼쳐보기' 류 버튼이 있으면 눌러서 접힌 상세 이미지까지 노출
    for label in ["상세정보 펼쳐보기", "상품정보 더보기", "펼쳐보기", "더보기"]:
        btn = page.get_by_text(label, exact=False).first
        try:
            if btn.is_visible(timeout=500):
                btn.click(timeout=2000)
                page.wait_for_timeout(1000)
                auto_scroll(page, steps=30)
                break
        except Exception:
            pass
    # 상세가 iframe 안에 있는 경우까지 포함해 모든 프레임 HTML 합침
    html = page.content()
    for fr in page.frames[1:]:
        try:
            html += "\n" + fr.content()
        except Exception:
            pass
    if debug:
        debug.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(debug / "coupang.png"))
        (debug / "coupang.html").write_text(html, encoding="utf-8")
    page.close()
    title, main, detail = coupang.extract_from_html(html, url)
    return coupang.CoupangProduct(pid, url, title, coupang.extract_seller(html), main, detail)


def run(args):
    out_root = Path(args.out)
    with open_context(Path(args.profile), headless=args.headless) as ctx:
        print("① 쿠팡 상품 읽는 중…")
        cp = fetch_coupang(ctx, args.target, Path(args.out) / "_debug" if args.debug else None)
        root = out_root / f"coupang_{cp.product_id}"
        debug = root / "_debug" if args.debug else None
        print(f"   {cp.title or '(제목 없음)'} — 대표 {len(cp.main_images)}장, 상세 {len(cp.detail_images)}장")
        if not cp.main_images:
            sys.exit("   쿠팡 대표 이미지를 찾지 못했습니다. --debug 로 다시 실행해 coupang.html 을 확인하세요.")

        c_files = download_all(cp.main_images, root / "coupang", "main_")
        c_files += download_all(cp.detail_images, root / "coupang", "detail_")
        if not c_files:
            sys.exit("   쿠팡 이미지 다운로드에 모두 실패했습니다(네트워크/차단 확인).")
        query_img = c_files[0]
        print(f"   저장 {len(c_files)}장 → {root / 'coupang'}  (검색용: {query_img.name})")

        print("② 타오바오 이미지검색 중…")
        items = taobao.image_search(ctx, query_img, limit=max(args.top * 4, 20), debug_dir=debug)
        print(f"   결과 {len(items)}개")

        report_items = []
        for it in items:
            tdir = root / "taobao" / it.item_id
            thumb = download_all([it.thumb], tdir, "thumb_") if it.thumb else []
            if thumb:
                it.similarity = similarity(query_img, thumb[0])
            report_items.append((it, thumb, tdir))

        report_items.sort(key=lambda x: -(x[0].similarity or 0))
        if args.min_sim is not None:
            report_items = [x for x in report_items if (x[0].similarity or 0) >= args.min_sim]

        taobao_report = []
        for rank, (it, files, tdir) in enumerate(report_items, 1):
            if not args.no_detail and rank <= args.top:
                print(f"③ [{rank}/{args.top}] {it.item_id} 상세 이미지 수집…")
                try:
                    it.images = taobao.item_images(ctx, it, debug_dir=debug)
                    files += download_all(it.images, tdir, "img_")
                except Exception as e:
                    print(f"   ! {e}")
                time.sleep(2)  # 과도한 요청 방지
            taobao_report.append({
                "item_id": it.item_id, "url": it.url, "title": it.title, "price": it.price,
                "similarity": it.similarity, "image_urls": it.images or [it.thumb],
                "files": [str(f.relative_to(root)) for f in files],
            })

    report = {
        "coupang": {"product_id": cp.product_id, "url": cp.url, "title": cp.title,
                    "seller": cp.seller,
                    "image_urls": cp.main_images + cp.detail_images,
                    "files": [str(f.relative_to(root)) for f in c_files]},
        "taobao": taobao_report,
    }
    write_report(root, report)
    print(f"\n완료 → {root / 'index.html'} (브라우저로 열어 확인), {root / 'results.json'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="finder", description="쿠팡 상품 → 타오바오 이미지검색 → 이미지 일괄 추출")
    ap.add_argument("target", help="쿠팡 상품 링크/번호, 또는 'login'")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", default="output")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--no-detail", action="store_true")
    ap.add_argument("--min-sim", type=float, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)
    if args.target == "login":
        cmd_login(Path(args.profile))
    else:
        run(args)


if __name__ == "__main__":
    main()
