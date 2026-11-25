import hashlib, hmac, json, time
from finder import partners


def test_authorization_format():
    t = time.strptime("2026-11-25 06:40:27", "%Y-%m-%d %H:%M:%S")
    h = partners.authorization("GET", partners.SEARCH_PATH, "keyword=a&limit=1", "AK", "SK", now=t)
    msg = "261125T064027Z" + "GET" + partners.SEARCH_PATH + "keyword=a&limit=1"
    sig = hmac.new(b"SK", msg.encode(), hashlib.sha256).hexdigest()
    assert h == f"CEA algorithm=HmacSHA256, access-key=AK, signed-date=261125T064027Z, signature={sig}"


def test_main_saves_banners(tmp_path, monkeypatch):
    class Resp:
        status_code = 200
        def json(self):
            return {"rCode": "0", "data": {"productData": [
                {"productId": 1111111, "productName": "상품A", "productPrice": 1000,
                 "productImage": "https://ads-partners.coupang.com/image1/a.jpg", "productUrl": "https://link.coupang.com/re/x"},
                {"productId": 2222222, "productName": "상품B", "productPrice": 2000,
                 "productImage": "https://ads-partners.coupang.com/image1/b.jpg", "productUrl": "https://link.coupang.com/re/y"},
            ]}}
    seen = {}
    def fake_get(url, headers, timeout):
        seen["url"], seen["auth"] = url, headers["Authorization"]
        return Resp()
    monkeypatch.setattr(partners.requests, "get", fake_get)
    monkeypatch.setattr(partners, "download_all", lambda urls, out, prefix: [out / f"{prefix}001.jpg"])
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK"); monkeypatch.setenv("COUPANG_SECRET_KEY", "SK")
    (tmp_path / "o" / "이어폰").mkdir(parents=True)
    partners.main(["이어폰", "--limit", "2", "--only", "https://www.coupang.com/vp/products/2222222", "--out", str(tmp_path / "o")])
    assert "keyword=%EC%9D%B4%EC%96%B4%ED%8F%B0&limit=2" in seen["url"]
    recs = json.loads((tmp_path / "o" / "이어폰" / "banners.json").read_text())
    assert [r["productId"] for r in recs] == [2222222] and recs[0]["partnersUrl"].startswith("https://link.coupang.com")
