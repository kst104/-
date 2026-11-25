import pytest
from finder import coupang, taobao


def test_parse_inputs():
    assert coupang.parse_input("7335597976")[0] == "7335597976"
    pid, url = coupang.parse_input("https://www.coupang.com/vp/products/7335597976?itemId=1&vendorItemId=2&q=x")
    assert pid == "7335597976" and url.endswith("?itemId=1&vendorItemId=2")
    assert coupang.parse_input("m.coupang.com/vm/products/123456")[0] == "123456"
    assert coupang.parse_input("https://link.coupang.com/a/abc")[0] == ""
    with pytest.raises(ValueError):
        coupang.parse_input("https://example.com/x")


def test_upscale():
    u = "//thumbnail6.coupangcdn.com/thumbnails/remote/492x492ex/image/a/b.jpg?x=1"
    assert coupang.upscale(u) == "https://thumbnail6.coupangcdn.com/thumbnails/remote/1000x1000ex/image/a/b.jpg"


def test_extract_html():
    html = """<html><head><meta property="og:title" content="테스트 상품 - 쿠팡!">
    <meta property="og:image" content="https://thumbnail1.coupangcdn.com/thumbnails/remote/492x492ex/image/p/main.jpg"></head>
    <body><img src="//thumbnail1.coupangcdn.com/thumbnails/remote/48x48ex/image/p/main.jpg">
    <img src="//thumbnail2.coupangcdn.com/thumbnails/remote/48x48ex/image/p/second.jpg">
    <img src="//image1.coupangcdn.com/image/badges/rocket_icon.png">
    <div id="productDetail"><img data-src="//thumbnail9.coupangcdn.com/thumbnails/remote/q89/image/retail/images/d1.jpg"></div>
    </body></html>"""
    title, main, detail = coupang.extract_from_html(html, "https://www.coupang.com/vp/products/1")
    assert title == "테스트 상품"
    assert len(main) == 2 and all("1000x1000ex" in m for m in main)
    assert detail == ["https://thumbnail9.coupangcdn.com/thumbnails/remote/q89/image/retail/images/d1.jpg"]


def test_taobao_helpers():
    assert taobao.original_image("//img.alicdn.com/bao/x/abc.jpg_220x220q90.jpg_.webp") == "https://img.alicdn.com/bao/x/abc.jpg"
    assert taobao.clean_item_url("https://detail.tmall.com/item.htm?spm=1&id=99&x=2", "99") == "https://detail.tmall.com/item.htm?id=99"
    assert taobao.item_id_from_url("https://item.taobao.com/item.htm?id=123") == "123"


def test_seller():
    assert coupang.extract_seller('<a class="prod-sale-vendor-name">좋은상점</a>') == "좋은상점"
    assert coupang.extract_seller('<script>{"vendorName":"ABC몰"}</script>') == "ABC몰"
    assert coupang.extract_seller("<p>없음</p>") == ""
