# 쿠팡 → 타오바오 이미지 추출기

쿠팡 상품번호 또는 링크를 넣으면 다음 순서로 진행합니다.
1. 쿠팡 상품 페이지의 대표 이미지와 상세 이미지를 저장합니다.
2. 대표 이미지로 타오바오 이미지검색(拍立淘)을 합니다.
3. 결과 상품을 유사도 순으로 정렬하고, 상위 N개 상품의 대표·SKU·상세 이미지를 모두 저장합니다.
4. 결과를 `index.html`(갤러리)과 `results.json`(원본 URL, 판매자, 가격, 유사도)로 만듭니다.

## 설치 (Mac / Windows, 본인 PC에서 실행)
```bash
cd taobao-image-finder
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 사용
```bash
python -m finder login                                   # 최초 1회: 타오바오 로그인 (QR)
python -m finder https://www.coupang.com/vp/products/7335597976
python -m finder 7335597976 --top 10 --min-sim 0.6 --out ~/Downloads/finder
```
결과는 `output/coupang_<상품번호>/`에 저장됩니다.
```
coupang/        main_*.jpg  detail_*.jpg
taobao/<상품ID>/ thumb_*.jpg  img_*.jpg
index.html      results.json
```

## 알아둘 점
- **로그인이 필요합니다.** 타오바오 이미지검색은 로그인해야 쓸 수 있습니다. 로그인 세션은 `~/.taobao-image-finder/profile`에 저장됩니다.
- **봇 차단이 있습니다.** 쿠팡은 자동화 접속을 자주 차단합니다. 그래서 브라우저 창을 띄운 채 실행하는 것이 기본입니다. 차단 화면이 나오면 직접 통과시킨 뒤 Enter를 누르세요.
- **화면이 바뀌면 고쳐야 합니다.** 두 사이트 모두 화면 구조를 자주 바꿉니다. 실패하면 `--debug`를 붙여 다시 실행하세요. `_debug/` 폴더에 저장되는 스크린샷과 HTML로 선택자를 고칠 수 있습니다.
- **판매자명은 없을 수도 있습니다.** 판매자명 추출은 최선 노력 방식이라 빈 값이 나올 수 있습니다.
- **이미지 해상도:** 쿠팡 대표 이미지는 썸네일 URL을 1000x1000 크기로 바꿔 요청합니다. 이것이 최대 원본인지는 확인하지 못했습니다.
- **권리:** 이미지 저작권은 판매자와 브랜드에 있습니다. 두 사이트 모두 약관에서 자동 수집을 제한합니다. 출처를 기록해도 사용 권리가 생기지는 않습니다.

## 테스트
```bash
pip install pytest && python -m pytest -q tests
```
