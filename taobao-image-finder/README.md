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

## 쿠팡 이미지만 받기 (API 키 불필요)
쿠팡 상품 페이지를 브라우저로 열어 대표 이미지와 상세 이미지를 저장합니다. 타오바오 검색은 하지 않습니다.
```bash
python -m finder.coupang_images https://www.coupang.com/vp/products/7335597976
python -m finder.coupang_images 7335597976 8123456789 --out ~/Downloads/coupang
python -m finder.coupang_images --file links.txt        # 한 줄에 링크나 번호 하나
```
결과는 `<out>/coupang_<번호>/`에 저장됩니다.
- `main_001.jpg`…, `detail_001.jpg`…
- `info.json`: 상품 URL, 상품명, 판매자, 각 이미지의 원본 URL
- `index.html`: 미리보기
`--no-detail`을 주면 대표 이미지만 받습니다.

### 이미 켜둔 브라우저로 받기 (`--cdp`)
원격 디버깅 포트를 지원하는 Chromium 계열 브라우저라면 새 창을 띄우지 않고 그 브라우저에 붙어서 받을 수 있습니다. 이때는 그 브라우저의 로그인 상태를 그대로 쓰고, 작업이 끝나도 브라우저를 닫지 않습니다.
```bash
"/Applications/<브라우저>.app/Contents/MacOS/<실행파일>" --remote-debugging-port=9222
python -m finder.coupang_images <링크> --cdp http://localhost:9222
```
Aside 브라우저가 이 방식을 지원하는지는 확인하지 못했습니다. 브라우저를 켠 뒤 `http://localhost:9222/json/version`이 열리면 지원하는 것입니다.

## 쿠팡파트너스 검색결과 배너 이미지만 받기
공식 파트너스 Open API를 사용합니다. 브라우저나 로그인이 필요 없고, 차단될 걱정도 적습니다.
```bash
export COUPANG_ACCESS_KEY=...  COUPANG_SECRET_KEY=...    # 파트너스 API 키 (최종 승인 회원만 발급)
python -m finder.partners "무선 이어폰" --limit 10
python -m finder.partners "무선 이어폰" --only https://www.coupang.com/vp/products/7335597976
```
결과는 `output/partners/<키워드>/`에 저장됩니다.
- `001_<상품번호>_001.jpg` 형식의 이미지 파일
- `banners.json`: 상품명, 가격, 파트너스 링크, 이미지 원본 URL

API에는 상품번호로 바로 조회하는 기능이 없습니다. 그래서 `--only`는 키워드로 검색한 뒤 결과에서 해당 상품만 골라냅니다. 시간당 호출 한도가 있으니 최신 한도는 파트너스 도움말에서 확인하세요.

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
