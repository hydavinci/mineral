"""Bounded, public-HTTP-only bookmark metadata extraction (stdlib only)."""
import gzip
import io
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

MAX_BYTES = 512 * 1024


class InvalidURL(ValueError):
    pass


def normalize_url(value):
    if not isinstance(value, str) or not value.strip():
        raise InvalidURL('请输入有效网址')
    value = value.strip()
    if any(ord(c) < 32 for c in value) or len(value) > 8192:
        raise InvalidURL('网址格式无效')
    if '://' not in value:
        value = 'https://' + value
    try:
        parts = urlsplit(value)
        port = parts.port
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username or parts.password or port not in (None, 80, 443)):
            raise ValueError()
        host = parts.hostname.encode('idna').decode('ascii')
        if ':' in host:
            host = '[' + host + ']'
        netloc = host + (':' + str(port) if port else '')
        return urlunsplit((parts.scheme, netloc, parts.path or '/', parts.query, ''))
    except (ValueError, UnicodeError):
        raise InvalidURL('仅支持有效的 HTTP/HTTPS 公网网址') from None


def validate_public_url(url):
    parts = urlsplit(normalize_url(url))
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise InvalidURL('不支持抓取本机或内网地址')


class PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = 4
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = normalize_url(newurl)
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts = []
        self.title_seen = False
        self.in_body = False
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = {key.lower(): value for key, value in attrs}
        if tag == 'body':
            self.in_body = True
        if tag == 'title' and not self.title_seen and not self.in_body:
            self.in_title = True
            self.title_seen = True
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            if attrs.get('content') and key not in self.meta:
                self.meta[key] = attrs['content']

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    def result(self):
        clean = lambda value: ' '.join(value.split())
        title = clean(''.join(self.title_parts)) or clean(self.meta.get('og:title', '') or self.meta.get('twitter:title', ''))
        desc = clean(self.meta.get('description', '') or self.meta.get('og:description', '') or self.meta.get('twitter:description', ''))
        return title[:1000], desc[:2000]


def parse_metadata(raw, charset=None):
    # Honor explicit HTTP charset first, then HTML charset; old Chinese sites use GBK.
    meta_charset = re.search(br'charset\s*=\s*["\']?\s*([\w-]+)', raw[:8192], re.I)
    candidates = [charset, meta_charset.group(1).decode('ascii') if meta_charset else None, 'utf-8', 'gb18030']
    text = None
    for encoding in candidates:
        if not encoding:
            continue
        try:
            text = raw.decode(encoding)
            break
        except (LookupError, UnicodeError):
            continue
    parser = MetadataParser()
    parser.feed(text if text is not None else raw.decode('utf-8', errors='replace'))
    return parser.result()


def fetch_metadata(value):
    url = normalize_url(value)
    fallback = urlsplit(url).hostname.removeprefix('www.')
    result = {'url': url, 'title': fallback, 'description': '', 'status': 'fallback', 'title_source': 'domain'}
    try:
        validate_public_url(url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirectHandler())
        request = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; MineralBookmark/1.0)',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Encoding': 'identity',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        with opener.open(request, timeout=8) as response:
            content_type = response.headers.get_content_type()
            if content_type not in ('text/html', 'application/xhtml+xml'):
                result['warning'] = '该链接不是 HTML 网页，请手动填写标题'
                return result
            raw = response.read(MAX_BYTES)
            if response.headers.get('Content-Encoding', '').lower() == 'gzip':
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                    raw = stream.read(MAX_BYTES)
            title, desc = parse_metadata(raw, response.headers.get_content_charset())
        # Do not report common anti-bot pages as successfully fetched site titles.
        if title.lower().strip(' .!') in ('just a moment', 'attention required | cloudflare', 'access denied', 'checking your browser', 'verify you are human'):
            result['warning'] = '目标网站需要浏览器验证，请手动填写标题'
            return result
        result['description'] = desc
        if title:
            result.update(title=title, title_source='page', status='ok')
        else:
            result['warning'] = '网页未提供可解析的标题，暂用域名，请手动确认'
    except InvalidURL:
        raise
    except urllib.error.HTTPError as exc:
        result['warning'] = f'目标网站返回 HTTP {exc.code}，暂用域名，请手动填写标题'
    except (TimeoutError, socket.timeout):
        result['warning'] = '目标网站响应超时，暂用域名，请手动填写标题'
    except (urllib.error.URLError, OSError, ValueError, EOFError):
        result['warning'] = '无法获取网页信息，暂用域名，请手动填写标题'
    return result
