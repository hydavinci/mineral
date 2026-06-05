#!/usr/bin/env python3
"""Mineral API - 极简书签管理接口"""
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

DATA_FILE = "/home/mineral/data/bookmarks.json"
API_TOKEN = "0824"


def load_bookmarks():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_bookmarks(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        token = self.headers.get("Authorization", "").replace("Bearer ", "")
        if token != API_TOKEN:
            self._json(401, {"error": "unauthorized"})
            return False
        return True

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/bookmarks":
            self._json(200, load_bookmarks())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/bookmarks":
            self._handle_add()
        elif self.path == "/api/fetch-meta":
            self._handle_fetch_meta()
        else:
            self._json(404, {"error": "not found"})

    def _handle_fetch_meta(self):
        """抓取 URL 的 title/description 用于自动填充"""
        if not self._auth():
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        url = body.get("url", "")
        if not url:
            self._json(400, {"error": "url required"})
            return

        import urllib.request
        import re
        import html as html_mod

        title = ""
        desc = ""
        raw_html = ""

        # Try multiple User-Agents
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        ]

        for ua in user_agents:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_html = resp.read(64000).decode("utf-8", errors="ignore")
                if raw_html:
                    break
            except Exception:
                continue

        if raw_html:
            # title
            m = re.search(r"<title[^>]*>([^<]+)</title>", raw_html, re.IGNORECASE)
            if m:
                title = html_mod.unescape(m.group(1).strip())
            # og:title fallback
            if not title:
                m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', raw_html, re.IGNORECASE)
                if m:
                    title = html_mod.unescape(m.group(1).strip())

            # meta description (multiple patterns)
            patterns = [
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            ]
            for pat in patterns:
                m = re.search(pat, raw_html, re.IGNORECASE)
                if m:
                    desc = html_mod.unescape(m.group(1).strip())
                    break

        # Fallback: derive title from URL
        if not title:
            from urllib.parse import urlparse as _urlparse
            parsed = _urlparse(url)
            title = parsed.hostname.replace("www.", "").split(".")[0].capitalize()

        # Fallback: if no description, try to get from search engine snippet
        if not desc:
            desc = self._fallback_desc_from_search(url, title)

        # Auto-categorize
        category = self._guess_category(url, title, desc)

        self._json(200, {"title": title, "description": desc, "category": category})

    def _guess_category(self, url, title, desc):
        """根据 URL/标题/描述猜测分类"""
        text = f"{url} {title} {desc}".lower()
        rules = [
            ("AI", ["ai", "machine learning", "llm", "gpt", "neural", "deep learning", "模型", "智能"]),
            ("Dev", ["developer", "github", "code", "programming", "framework", "api", "sdk", "开发"]),
            ("Design", ["design", "figma", "ui", "ux", "color", "font", "设计"]),
            ("Tools", ["tool", "utility", "converter", "generator", "dashboard", "manage", "工具"]),
            ("Reading", ["blog", "article", "essay", "magazine", "阅读", "博客"]),
            ("News", ["news", "新闻", "资讯"]),
            ("Fun", ["game", "fun", "play", "entertainment", "游戏"]),
            ("Infra", ["cloud", "server", "cdn", "dns", "hosting", "cloudflare", "aws", "azure"]),
        ]
        for cat, keywords in rules:
            if any(kw in text for kw in keywords):
                return cat
        return "Uncategorized"

    def _fallback_desc_from_search(self, url, title):
        """通过域名和标题推断一句描述"""
        from urllib.parse import urlparse as _urlparse
        parsed = _urlparse(url)
        domain = parsed.hostname.replace("www.", "") if parsed.hostname else ""

        # Well-known sites
        known = {
            "dash.cloudflare.com": "Cloudflare Dashboard — manage DNS, CDN, security, and performance for your websites",
            "github.com": "The world's largest platform for code hosting, collaboration, and open source",
            "cloudflare.com": "Web performance and security company providing CDN, DDoS protection, and DNS services",
            "vercel.com": "Frontend cloud platform for deploying web apps with zero configuration",
            "figma.com": "Collaborative design tool for building user interfaces and prototypes",
            "notion.so": "All-in-one workspace for notes, docs, wikis, and project management",
            "linear.app": "Streamlined issue tracking and project management for software teams",
            "youtube.com": "Video sharing and streaming platform",
            "twitter.com": "Social media platform for real-time news and conversations",
            "x.com": "Social media platform for real-time news and conversations",
            "makerworld.com": "3D printing model sharing community by Bambu Lab — discover and share printable designs",
            "thingiverse.com": "One of the largest 3D printing communities for sharing digital designs",
            "printables.com": "3D model repository by Prusa — free STL files for 3D printing",
            "reddit.com": "Social news aggregation, web content rating, and discussion platform",
            "stackoverflow.com": "Q&A community for programmers and developers",
            "huggingface.co": "AI community and platform for sharing machine learning models and datasets",
            "arxiv.org": "Open access archive for scientific papers in physics, math, CS, and more",
            "producthunt.com": "Platform to discover and share new tech products and startups",
            "dribbble.com": "Community for designers to share, grow, and get hired",
            "codepen.io": "Online code editor and front-end web development playground",
            "netlify.com": "Platform for deploying and hosting modern web projects",
            "supabase.com": "Open source Firebase alternative with PostgreSQL database",
            "railway.app": "Infrastructure platform for deploying apps and databases",
            "openai.com": "AI research company behind ChatGPT, GPT-4, and DALL-E",
            "anthropic.com": "AI safety company and creator of Claude AI assistant",
            "cursor.com": "AI-powered code editor for software development",
            "v0.dev": "AI-powered UI generation tool by Vercel",
            "replit.com": "Online IDE and collaborative coding platform",
        }

        for k, v in known.items():
            if k in (domain or "") or k in url:
                return v

        # Generic fallback from title
        if title and title.lower() not in ["home", "index", domain.split('.')[0]]:
            return f"{title} — {domain}"
        return ""

    def _handle_add(self):
        if not self._auth():
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        # Validate
        if not body.get("url"):
            self._json(400, {"error": "url is required"})
            return

        bookmark = {
            "title": body.get("title", ""),
            "url": body["url"],
            "description": body.get("description", ""),
            "category": body.get("category", "Uncategorized"),
            "tags": body.get("tags", []),
            "added": datetime.now().strftime("%Y-%m-%d"),
            "favicon": body.get("favicon", ""),
        }

        bookmarks = load_bookmarks()
        bookmarks.append(bookmark)
        save_bookmarks(bookmarks)
        self._json(201, bookmark)

    def do_PUT(self):
        if not self.path.startswith("/api/bookmarks"):
            self._json(404, {"error": "not found"})
            return
        if not self._auth():
            return

        params = parse_qs(urlparse(self.path).query)
        idx = int(params.get("index", [-1])[0])

        bookmarks = load_bookmarks()
        if idx < 0 or idx >= len(bookmarks):
            self._json(400, {"error": "invalid index"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        # Merge fields
        for key in ["title", "url", "description", "category", "tags", "favicon"]:
            if key in body:
                bookmarks[idx][key] = body[key]

        save_bookmarks(bookmarks)
        self._json(200, bookmarks[idx])

    def do_DELETE(self):
        if not self.path.startswith("/api/bookmarks"):
            self._json(404, {"error": "not found"})
            return
        if not self._auth():
            return

        # Delete by index: /api/bookmarks?index=0
        params = parse_qs(urlparse(self.path).query)
        idx = int(params.get("index", [-1])[0])

        bookmarks = load_bookmarks()
        if idx < 0 or idx >= len(bookmarks):
            self._json(400, {"error": "invalid index"})
            return

        removed = bookmarks.pop(idx)
        save_bookmarks(bookmarks)
        self._json(200, {"removed": removed})

    def log_message(self, format, *args):
        pass  # Silent


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 3721), Handler)
    print("Mineral API running on :3721")
    server.serve_forever()
