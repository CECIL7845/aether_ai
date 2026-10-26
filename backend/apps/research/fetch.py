"""SSRF-hardened page fetching and readable-text extraction.

Every URL (including each redirect hop) must be http(s) on a standard port and resolve only to public IP
addresses; private, loopback, link-local (cloud metadata), multicast and reserved ranges are refused. robots.txt
is honoured. Responses are size- and time-limited and only text/HTML is read.

Residual risk: DNS can change between our check and the connection (rebinding). Deployments that need stronger
guarantees should route outbound fetches through an egress proxy that enforces the same policy.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from django.conf import settings

USER_AGENT = "AetherResearchBot/0.1 (+self-hosted AI assistant; respects robots.txt)"
MAX_REDIRECTS = 4


class FetchError(Exception):
    pass


Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror as e:
        raise FetchError("The address could not be resolved.") from e


def is_public_ip(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def validate_url(url: str, resolver: Resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https links can be opened.")
    if parts.username or parts.password:
        raise FetchError("Links containing credentials are not opened.")
    if not parts.hostname:
        raise FetchError("The link has no host.")
    if parts.port not in (None, 80, 443):
        raise FetchError("Only standard web ports are allowed.")
    if settings.WEB_FETCH_BLOCK_PRIVATE_NETWORKS:
        ips = resolver(parts.hostname)
        if not ips or not all(is_public_ip(ip) for ip in ips):
            raise FetchError("This address points to a private or reserved network and was blocked.")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe", "template"}
    BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "pre",
             "blockquote", "table", "ul", "ol", "main"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        out, blank = [], False
        for line in lines:
            if line:
                out.append(line)
                blank = False
            elif not blank:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return " ".join(parser.title.split()), parser.text()


@dataclass(frozen=True)
class RawResponse:
    url: str
    status_code: int
    content_type: str
    charset: str
    body: bytes

    @property
    def text(self) -> str:
        try:
            return self.body.decode(self.charset or "utf-8", errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Page:
    url: str  # final URL after redirects
    title: str
    text: str


class Fetcher:
    def __init__(self, resolver: Resolver = system_resolver, transport: httpx.BaseTransport | None = None):
        self.resolver = resolver
        self.client = httpx.Client(
            transport=transport, follow_redirects=False, timeout=settings.WEB_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"},
        )
        self._robots: dict[str, RobotFileParser | None] = {}

    def close(self):
        self.client.close()

    def _get(self, url: str) -> RawResponse:
        """GET with manual redirects so every hop is validated, reading at most WEB_FETCH_MAX_BYTES."""
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(url, self.resolver)
            with self.client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > settings.WEB_FETCH_MAX_BYTES:
                        raise FetchError("The page is too large to read.")
                content_type = response.headers.get("content-type", "")
                return RawResponse(
                    url=url,
                    status_code=response.status_code,
                    content_type=content_type.split(";")[0].strip().lower(),
                    charset=response.charset_encoding or "",
                    body=bytes(body),
                )
        raise FetchError("Too many redirects.")

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                response = self._get(origin + "/robots.txt")
                if response.status_code >= 400:
                    parser = None  # no robots.txt: allowed
                else:
                    parser.parse(response.text.splitlines())
            except (FetchError, httpx.HTTPError):
                parser = None
            self._robots[origin] = parser
        robots = self._robots[origin]
        return robots is None or robots.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> Page:
        if not self.allowed_by_robots(url):
            raise FetchError("The site's robots.txt does not allow automated access to this page.")
        try:
            response = self._get(url)
        except httpx.TimeoutException as e:
            raise FetchError("The page took too long to respond.") from e
        except httpx.HTTPError as e:
            raise FetchError("The page could not be retrieved.") from e
        if response.status_code >= 400:
            raise FetchError(f"The page returned HTTP {response.status_code}.")
        content_type = response.content_type
        if content_type not in ("text/html", "application/xhtml+xml", "text/plain", ""):
            raise FetchError(f"Unsupported content type ({content_type}).")
        text = response.text
        if content_type == "text/plain":
            title, body = "", text
        else:
            title, body = html_to_text(text)
        if len(body) < 200:
            raise FetchError("The page had too little readable text (it may require JavaScript or a login).")
        return Page(url=response.url, title=title, text=body[: settings.WEB_FETCH_MAX_CHARS])
