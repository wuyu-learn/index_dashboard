from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROXY_BENCHMARK_NETWORK = ipaddress.ip_network("198.18.0.0/15")
BENCHMARK_PROXY_HOSTS = {"so.html5.qq.com"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
}
IGNORED_TEXT_TAGS = {"script", "style", "noscript"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class StructuredArticleParser(HTMLParser):
    """按元素 id、class 或标签提取标题、来源和正文。"""

    def __init__(
        self,
        *,
        title_ids: Sequence[str] = (),
        title_classes: Sequence[str] = (),
        title_tags: Sequence[str] = (),
        source_ids: Sequence[str] = (),
        source_classes: Sequence[str] = (),
        content_ids: Sequence[str] = (),
        content_classes: Sequence[str] = (),
        content_tags: Sequence[str] = (),
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, str, Set[str]]] = []
        self.title_ids = set(title_ids)
        self.title_classes = set(title_classes)
        self.title_tags = set(title_tags)
        self.source_ids = set(source_ids)
        self.source_classes = set(source_classes)
        self.content_ids = set(content_ids)
        self.content_classes = set(content_classes)
        self.content_tags = set(content_tags)
        self.title_parts: List[str] = []
        self.source_parts: List[str] = []
        self.content_parts: List[str] = []
        self.meta_title = ""
        self.meta_source = ""

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id", "")
        classes = set(attributes.get("class", "").split())
        if tag == "meta":
            self._handle_meta(attributes)
        if tag == "br" and self._inside_content():
            self.content_parts.append("\n")
        if tag not in VOID_TAGS:
            self.stack.append((tag, element_id, classes))
        if tag in {"p", "div", "section", "li"} and self._inside_content():
            self.content_parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: List[tuple]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if any(tag in IGNORED_TEXT_TAGS for tag, _, _ in self.stack):
            return
        if self._inside(
            self.title_ids,
            self.title_classes,
            self.title_tags,
        ):
            self.title_parts.append(data)
        if self._inside(
            self.source_ids,
            self.source_classes,
            set(),
        ):
            self.source_parts.append(data)
        if self._inside_content():
            self.content_parts.append(data)

    def _handle_meta(self, attrs: Dict[str, Optional[str]]) -> None:
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        value = attrs.get("content") or ""
        if key in {"og:title", "twitter:title"} and not self.meta_title:
            self.meta_title = value
        if key in {"author", "article:author"} and not self.meta_source:
            self.meta_source = value

    def _inside_content(self) -> bool:
        return self._inside(
            self.content_ids,
            self.content_classes,
            self.content_tags,
        )

    def _inside(
        self,
        ids: Set[str],
        classes: Set[str],
        tags: Set[str],
    ) -> bool:
        return any(
            element_id in ids
            or bool(element_classes.intersection(classes))
            or tag in tags
            for tag, element_id, element_classes in self.stack
        )

    def result(self) -> Dict[str, str]:
        return {
            "title": clean_text("".join(self.title_parts))
            or clean_text(self.meta_title),
            "source": clean_text("".join(self.source_parts))
            or clean_text(self.meta_source),
            "content": clean_text("".join(self.content_parts)),
        }


class ArticlePageParser:
    name = "base"

    def supports(self, url: str, html: str) -> bool:
        raise NotImplementedError

    def parse(self, url: str, html: str) -> Dict[str, str]:
        raise NotImplementedError


class TencentNewsParser(ArticlePageParser):
    name = "tencent_news"

    def supports(self, url: str, html: str) -> bool:
        return (
            urlparse(url).hostname == "new.qq.com"
            or 'id="article-content"' in html
        )

    def parse(self, url: str, html: str) -> Dict[str, str]:
        parser = StructuredArticleParser(
            title_ids=("article-title",),
            source_classes=("media-name",),
            content_ids=("article-content",),
            content_classes=("rich_media_content",),
        )
        parser.feed(html)
        return parser.result()


class TencentSearchNewsParser(ArticlePageParser):
    name = "tencent_search_news"

    def supports(self, url: str, html: str) -> bool:
        return (
            urlparse(url).hostname == "so.html5.qq.com"
            or 'class="article-content"' in html
        )

    def parse(self, url: str, html: str) -> Dict[str, str]:
        parser = StructuredArticleParser(
            title_classes=("article-title",),
            source_classes=("article-user-right-title",),
            content_classes=("article-content",),
        )
        parser.feed(html)
        return parser.result()


class GenericArticleParser(ArticlePageParser):
    name = "generic"

    def supports(self, url: str, html: str) -> bool:
        return True

    def parse(self, url: str, html: str) -> Dict[str, str]:
        parser = StructuredArticleParser(
            title_tags=("h1",),
            source_classes=("author", "source"),
            content_tags=("article", "main"),
        )
        parser.feed(html)
        return parser.result()


class ArticleParserRegistry:
    def __init__(
        self,
        parsers: Optional[Sequence[ArticlePageParser]] = None,
    ) -> None:
        self.parsers = list(
            parsers
            or (
                TencentNewsParser(),
                TencentSearchNewsParser(),
                GenericArticleParser(),
            )
        )

    def parse(self, url: str, html: str) -> Dict[str, str]:
        attempted = []
        fallback: Optional[Dict[str, str]] = None
        for parser in self.parsers:
            if not parser.supports(url, html):
                continue
            article = parser.parse(url, html)
            attempted.append(parser.name)
            article["parser"] = parser.name
            if fallback is None:
                fallback = article
            if article["content"]:
                return article
        result = fallback or {"title": "", "source": "", "content": ""}
        result["parser"] = ",".join(attempted) or "none"
        return result


def fetch_article(
    url: str,
    registry: Optional[ArticleParserRegistry] = None,
) -> Dict[str, Any]:
    validate_public_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise RuntimeError(f"不支持的正文类型：{content_type}")
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise RuntimeError("网页内容超过 2MB 限制")
            charset = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
    except Exception as exc:
        return {
            "url": url,
            "fetchStatus": "failed",
            "error": str(exc),
            "title": "",
            "source": "",
            "content": "",
            "contentSource": "none",
            "parser": "none",
        }

    article = (registry or ArticleParserRegistry()).parse(url, html)
    article.update(
        {
            "url": url,
            "fetchStatus": (
                "success" if article["content"] else "empty"
            ),
            "contentSource": (
                "webpage" if article["content"] else "none"
            ),
        }
    )
    return article


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("候选链接不是有效的 HTTP(S) 地址")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost"} or hostname.endswith(".local"):
        raise RuntimeError("不允许访问本地地址")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = socket.getaddrinfo(hostname, parsed.port or default_port)
    except socket.gaierror as exc:
        raise RuntimeError(f"无法解析候选链接域名：{hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            hostname in BENCHMARK_PROXY_HOSTS
            and ip in PROXY_BENCHMARK_NETWORK
        ):
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise RuntimeError("候选链接解析到不安全的本地或私有地址")
