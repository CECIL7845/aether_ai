import httpx
import pytest

from apps.research.fetch import Fetcher, FetchError, html_to_text, is_public_ip, validate_url

PUBLIC = "93.184.216.34"
DNS = {"example.test": [PUBLIC], "news.test": [PUBLIC], "evil.test": ["10.0.0.5"], "mixed.test": [PUBLIC, "127.0.0.1"]}
PAGE = "<html><head><title>Cocoa prices</title><script>steal()</script></head><body><nav>Menu</nav>" + (
    "<article><h1>Cocoa in 2026</h1><p>Ghana cocoa farmgate prices rose this season.</p>" * 10
) + "<footer>Copyright</footer></body></html>"


def resolver(host):
    if host not in DNS:
        raise FetchError("unresolvable")
    return DNS[host]


def fetcher(routes: dict[str, httpx.Response]) -> Fetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return Fetcher(resolver=resolver, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1", "fc00::1",
           "::ffff:127.0.0.1", "0.0.0.0", "224.0.0.1", "100.64.0.1"],
)
def test_private_and_reserved_addresses_are_not_public(ip):
    assert not is_public_ip(ip)


def test_public_address():
    assert is_public_ip(PUBLIC)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "http and https"),
        ("ftp://example.test/x", "http and https"),
        ("http://user:pw@example.test/", "credentials"),
        ("http://example.test:8080/", "standard web ports"),
        ("http://evil.test/", "private or reserved"),
        ("http://mixed.test/", "private or reserved"),  # any private answer blocks the host
    ],
)
def test_validate_url_blocks_unsafe_targets(url, reason):
    with pytest.raises(FetchError, match=reason):
        validate_url(url, resolver)


def test_fetch_extracts_readable_text_without_scripts_or_navigation():
    f = fetcher({"https://example.test/robots.txt": httpx.Response(404),
                 "https://example.test/cocoa": httpx.Response(200, html=PAGE)})
    page = f.fetch("https://example.test/cocoa")
    assert page.title == "Cocoa prices"
    assert "farmgate prices rose" in page.text and "## Cocoa in 2026" in page.text
    assert "steal()" not in page.text and "Menu" not in page.text and "Copyright" not in page.text


def test_redirect_into_private_network_is_blocked():
    f = fetcher({"https://example.test/robots.txt": httpx.Response(404),
                 "https://example.test/go": httpx.Response(302, headers={"location": "http://evil.test/admin"})})
    with pytest.raises(FetchError, match="private or reserved"):
        f.fetch("https://example.test/go")


def test_redirect_loop_is_bounded():
    f = fetcher({"https://example.test/robots.txt": httpx.Response(404),
                 "https://example.test/a": httpx.Response(302, headers={"location": "/a"})})
    with pytest.raises(FetchError, match="Too many redirects"):
        f.fetch("https://example.test/a")


def test_robots_txt_is_respected():
    f = fetcher({"https://example.test/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private"),
                 "https://example.test/private/x": httpx.Response(200, html=PAGE)})
    with pytest.raises(FetchError, match="robots.txt"):
        f.fetch("https://example.test/private/x")


def test_oversized_and_non_text_responses_are_refused(settings):
    settings.WEB_FETCH_MAX_BYTES = 1000
    f = fetcher({"https://example.test/robots.txt": httpx.Response(404),
                 "https://example.test/big": httpx.Response(200, html="<p>x</p>" * 1000),
                 "https://example.test/file.zip": httpx.Response(200, content=b"PK..",
                                                                 headers={"content-type": "application/zip"})})
    with pytest.raises(FetchError, match="too large"):
        f.fetch("https://example.test/big")
    with pytest.raises(FetchError, match="Unsupported content type"):
        f.fetch("https://example.test/file.zip")


def test_error_status_and_empty_pages():
    f = fetcher({"https://example.test/robots.txt": httpx.Response(404),
                 "https://example.test/js-app": httpx.Response(200, html="<div id=root></div>")})
    with pytest.raises(FetchError, match="HTTP 404"):
        f.fetch("https://example.test/missing")
    with pytest.raises(FetchError, match="too little readable text"):
        f.fetch("https://example.test/js-app")


def test_html_to_text_collapses_whitespace():
    title, text = html_to_text("<title> A  B </title><p>one</p><p>two   three</p>")
    assert title == "A B" and text == "one\n\ntwo three"
