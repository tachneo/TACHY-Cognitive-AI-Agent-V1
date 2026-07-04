"""Web explorer — the brain's safe window to the internet (Phase 1O).

Read-only: search the web (DuckDuckGo HTML, no API key) and fetch public pages
as plain text. Hard safety rails:

- http/https only; every hop (including redirects) must resolve to a PUBLIC IP,
  so the tool can never be steered at localhost / LAN / cloud metadata (SSRF).
- Response size and timeout caps.
- Fetched content is UNTRUSTED DATA: sanitize_untrusted() neutralizes obvious
  prompt-injection lines before anything reaches the LLM.
"""
from __future__ import annotations

import base64
import html as html_lib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlparse, unquote

import httpx

from app.config import get_settings

_MAX_REDIRECTS = 4

# Lines containing these phrases in fetched pages are neutralized before the
# text can reach the LLM prompt.
_INJECTION_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
        r"disregard (all |any )?(previous|prior|above)",
        r"you are now\b",
        r"new instructions?:",
        r"system prompt",
        r"reveal (your|the) (prompt|instructions|api key|secrets?)",
        r"\bexecute\b.{0,30}\b(command|shell|code)\b",
    )
]

_TAG_SCRIPT = re.compile(r"<(script|style|noscript|svg|head)\b.*?</\1>", re.S | re.I)
_TAG_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK = re.compile(r"\n{3,}")


@dataclass
class Page:
    url: str
    title: str = ""
    text: str = ""
    ok: bool = False
    error: str = ""
    injection_flags: int = 0


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass
class UrlCheck:
    allowed: bool
    reason: str = ""
    resolved_ip: str = ""
    host: str = ""
    parsed: object = field(default=None, repr=False)


def check_url(url: str) -> UrlCheck:
    """Allow only http(s) URLs whose host resolves to a public IP."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return UrlCheck(False, "unparseable url")
    if parsed.scheme not in {"http", "https"}:
        return UrlCheck(False, f"scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname or ""
    if not host:
        return UrlCheck(False, "no host")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return UrlCheck(False, "local host blocked")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        return UrlCheck(False, f"dns failure: {exc}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return UrlCheck(False, f"non-public address blocked ({ip})", str(ip), host)
    resolved = infos[0][4][0] if infos else ""
    return UrlCheck(True, "ok", resolved, host, parsed)


def html_to_text(raw: str) -> tuple[str, str]:
    """Return (title, plain_text) from an HTML document. Regex-based on purpose:
    no new dependency, and good enough for learning digests."""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = html_lib.unescape(_TAG_ANY.sub("", title_m.group(1)).strip()) if title_m else ""
    body = _TAG_SCRIPT.sub(" ", raw)
    # Keep paragraph structure: block-level closers become newlines.
    body = re.sub(r"</(p|div|li|h[1-6]|tr|section|article|br)[^>]*>", "\n", body, flags=re.I)
    body = _TAG_ANY.sub(" ", body)
    body = html_lib.unescape(body)
    body = _WS.sub(" ", body)
    body = "\n".join(line.strip() for line in body.splitlines())
    body = _BLANK.sub("\n\n", body).strip()
    return title, body


def sanitize_untrusted(text: str) -> tuple[str, int]:
    """Neutralize likely prompt-injection lines. Returns (clean_text, flags)."""
    flags = 0
    out: list[str] = []
    for line in text.splitlines():
        if any(p.search(line) for p in _INJECTION_PATTERNS):
            flags += 1
            out.append("[line removed: possible prompt injection]")
        else:
            out.append(line)
    return "\n".join(out), flags


def fetch_page(url: str, *, max_bytes: int | None = None,
               timeout: float | None = None) -> Page:
    """Fetch one public web page as sanitized plain text.

    Redirects are followed manually so EVERY hop passes check_url — a public
    page cannot redirect the brain into a private network.
    """
    s = get_settings()
    max_bytes = max_bytes or s.web_learning_max_bytes
    timeout = timeout or s.web_learning_fetch_timeout
    headers = {"User-Agent": s.web_learning_user_agent,
               "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"}

    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        chk = check_url(current)
        if not chk.allowed:
            return Page(url=current, error=f"blocked: {chk.reason}")
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                with client.stream("GET", current, headers=headers) as resp:
                    if resp.status_code in {301, 302, 303, 307, 308}:
                        loc = resp.headers.get("location", "")
                        if not loc:
                            return Page(url=current, error="redirect without location")
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code >= 400:
                        return Page(url=current, error=f"http {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").lower()
                    if not any(t in ctype for t in ("text/html", "text/plain",
                                                    "application/xhtml", "application/xml")):
                        return Page(url=current, error=f"unsupported content-type: {ctype}")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= max_bytes:
                            break
                    raw = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            return Page(url=current, error=f"fetch failed: {type(exc).__name__}")
        title, text = html_to_text(raw) if "html" in ctype or "xml" in ctype \
            else ("", raw)
        text, flags = sanitize_untrusted(text)
        return Page(url=current, title=title[:300], text=text,
                    ok=True, injection_flags=flags)
    return Page(url=current, error="too many redirects")


_DDG_URL = "https://html.duckduckgo.com/html/"
_DDG_RESULT = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.S | re.I,
)
_DDG_SNIPPET = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.S | re.I,
)


def _decode_ddg_href(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded-url>."""
    href = html_lib.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


def _search_result_url_allowed(url: str) -> bool:
    """Cheap parser-time filter; fetch_page still performs DNS SSRF checks."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def parse_ddg_html(raw: str, max_results: int = 5) -> list[SearchResult]:
    links = _DDG_RESULT.findall(raw)
    snippets = [html_lib.unescape(_TAG_ANY.sub("", s)).strip()
                for s in _DDG_SNIPPET.findall(raw)]
    results: list[SearchResult] = []
    for i, (href, title_html) in enumerate(links):
        url = _decode_ddg_href(href)
        if not _search_result_url_allowed(url):
            continue
        title = html_lib.unescape(_TAG_ANY.sub("", title_html)).strip()
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(SearchResult(title=title, url=url, snippet=snippet[:400]))
        if len(results) >= max_results:
            break
    return results


def _search_ddg(query: str, max_results: int) -> list[SearchResult]:
    resp = httpx.post(
        _DDG_URL,
        data={"q": query},
        headers={"User-Agent": _SEARCH_UA},
        timeout=get_settings().web_learning_fetch_timeout,
    )
    resp.raise_for_status()
    return parse_ddg_html(resp.text, max_results=max_results)


# Bing wraps result links as /ck/a?...&u=a1<base64url-of-real-url>.
_BING_RESULT = re.compile(r"<h2[^>]*><a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a></h2>", re.S)


def _decode_bing_href(href: str) -> str:
    href = html_lib.unescape(href)
    parsed = urlparse(href)
    if "bing.com" in (parsed.hostname or "") and parsed.path.startswith("/ck/"):
        enc = parse_qs(parsed.query).get("u", [""])[0]
        if enc.startswith("a1"):
            try:
                return base64.urlsafe_b64decode(enc[2:] + "==").decode("utf-8", "replace")
            except (ValueError, UnicodeDecodeError):
                return ""
    return href


def parse_bing_html(raw: str, max_results: int = 5) -> list[SearchResult]:
    results: list[SearchResult] = []
    for href, title_html in _BING_RESULT.findall(raw):
        url = _decode_bing_href(href)
        if not url or not _search_result_url_allowed(url):
            continue
        title = html_lib.unescape(_TAG_ANY.sub("", title_html)).strip()
        results.append(SearchResult(title=title, url=url))
        if len(results) >= max_results:
            break
    return results


def _search_bing(query: str, max_results: int) -> list[SearchResult]:
    resp = httpx.get(
        "https://www.bing.com/search",
        params={"q": query},
        headers={"User-Agent": _SEARCH_UA},
        timeout=get_settings().web_learning_fetch_timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_bing_html(resp.text, max_results=max_results)


def _search_wikipedia(query: str, max_results: int) -> list[SearchResult]:
    resp = httpx.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query,
                "srlimit": max_results, "format": "json"},
        headers={"User-Agent": _SEARCH_UA},
        timeout=get_settings().web_learning_fetch_timeout,
    )
    resp.raise_for_status()
    hits = resp.json().get("query", {}).get("search", [])
    return [
        SearchResult(
            title=h.get("title", ""),
            url="https://en.wikipedia.org/wiki/"
                + (h.get("title", "").replace(" ", "_")),
            snippet=_TAG_ANY.sub("", h.get("snippet", ""))[:400],
        )
        for h in hits
    ]


# Search engines get a browser UA: DDG/Bing serve bot-challenge pages to bot
# UAs. Page fetches keep the honest TachyBrainBot UA.
_SEARCH_UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
              "Gecko/20100101 Firefox/128.0")

_ENGINES = (_search_ddg, _search_bing, _search_wikipedia)


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Keyless web search. Tries DuckDuckGo, then Bing, then Wikipedia — some
    engines IP-block servers (DDG returns a 202 challenge from this VPS)."""
    for engine in _ENGINES:
        try:
            results = engine(query, max_results)
        except (httpx.HTTPError, ValueError):
            continue
        if results:
            return results
    return []
