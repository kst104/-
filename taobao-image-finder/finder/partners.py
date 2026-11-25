"""쿠팡파트너스 Open API 상품검색 → 검색결과 배너(상품) 이미지만 추출.

사용:
  export COUPANG_ACCESS_KEY=...  COUPANG_SECRET_KEY=...   # 파트너스 > 추가기능 > API 에서 발급(최종승인 회원만)
  python -m finder.partners "무선 이어폰"                  # 키워드 검색
  python -m finder.partners "무선 이어폰" --limit 5 --out banners
  python -m finder.partners "무선 이어폰" --only https://www.coupang.com/vp/products/7335597976
      → 검색결과 중 해당 상품번호만 저장 (API에 '상품번호로 조회' 기능은 없어 키워드 검색 후 거른다)

결과: <out>/<키워드>/001_<상품번호>.jpg ... + banners.json (상품명, 가격, 파트너스 링크, 이미지 원본 URL)

호출 제한: 파트너스 API는 시간당 호출 횟수 제한이 있고 초과 시 일정 시간 사용이 막힌다.
정확한 한도는 파트너스 도움말의 최신 공지를 확인할 것(이 코드는 1회 실행 = 검색 API 1회 호출).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from .coupang import parse_input
from .download import download_all

DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"


def authorization(method: str, path: str, query: str, access_key: str, secret_key: str,
                  now: time.struct_time | None = None) -> str:
    """쿠팡 Open API HMAC 서명 헤더 (공식 문서 형식: CEA algorithm=HmacSHA256, ...)."""
    now = now or time.gmtime()
    signed_date = time.strftime("%y%m%dT%H%M%SZ", now)
    message = signed_date + method + path + query
    sig = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={signed_date}, signature={sig}"


def search(keyword: str, limit: int, access_key: str, secret_key: str, sub_id: str = "") -> list[dict]:
    params = {"keyword": keyword, "limit": limit}
    if sub_id:
        params["subId"] = sub_id
    query = urlencode(params)
    headers = {
        "Authorization": authorization("GET", SEARCH_PATH, query, access_key, secret_key),
        "Content-Type": "application/json;charset=UTF-8",
    }
    r = requests.get(f"{DOMAIN}{SEARCH_PATH}?{query}", headers=headers, timeout=30)
    try:
        body = r.json()
    except ValueError:
        raise RuntimeError(f"API 응답 해석 실패 (HTTP {r.status_code}): {r.text[:300]}")
    if r.status_code != 200 or str(body.get("rCode", "0")) != "0":
        raise RuntimeError(f"API 오류 (HTTP {r.status_code}): {body.get('rMessage') or body}")
    data = body.get("data") or {}
    # 응답 형식: data.productData[] (일부 예제는 data 자체가 리스트) → 둘 다 처리
    items = data.get("productData", []) if isinstance(data, dict) else data
    return items or []


def safe_name(s: str) -> str:
    return re.sub(r"[^\w가-힣.-]+", "_", s).strip("_")[:40] or "search"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="finder.partners", description="쿠팡파트너스 검색결과 배너 이미지 추출")
    ap.add_argument("keyword", help="검색어")
    ap.add_argument("--limit", type=int, default=10, help="검색 결과 수 (기본 10)")
    ap.add_argument("--only", action="append", default=[], help="이 상품번호/링크만 저장 (여러 번 지정 가능)")
    ap.add_argument("--sub-id", default="", help="파트너스 subId (채널 구분용, 선택)")
    ap.add_argument("--out", default="output/partners")
    args = ap.parse_args(argv)

    ak, sk = os.environ.get("COUPANG_ACCESS_KEY"), os.environ.get("COUPANG_SECRET_KEY")
    if not ak or not sk:
        sys.exit("COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 환경변수를 설정하세요 (파트너스 API 키).")

    items = search(args.keyword, args.limit, ak, sk, args.sub_id)
    if args.only:
        want = {parse_input(x)[0] for x in args.only}
        items = [i for i in items if str(i.get("productId")) in want]
    if not items:
        sys.exit("저장할 검색결과가 없습니다.")

    out = Path(args.out) / safe_name(args.keyword)
    records = []
    for rank, it in enumerate(items, 1):
        img = it.get("productImage")
        if not img:
            continue
        files = download_all([img], out, f"{rank:03d}_{it.get('productId')}_")
        records.append({
            "rank": rank,
            "productId": it.get("productId"),
            "productName": it.get("productName"),
            "productPrice": it.get("productPrice"),
            "isRocket": it.get("isRocket"),
            "partnersUrl": it.get("productUrl"),   # 파트너스 추적 링크
            "imageUrl": img,
            "file": files[0].name if files else None,
        })
        print(f"{rank:>3}. {it.get('productName')}  → {files[0].name if files else '다운로드 실패'}")
    (out / "banners.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료 → {out} ({sum(1 for r in records if r['file'])}장), {out / 'banners.json'}")


if __name__ == "__main__":
    main()
