#!/usr/bin/env python3
"""Mineral API - 极简书签管理接口"""
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from metadata import fetch_metadata, InvalidURL

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
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 16384:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
            meta = fetch_metadata(body.get("url", ""))
        except InvalidURL as exc:
            self._json(400, {"error": str(exc)})
            return
        except (ValueError, TypeError):
            self._json(400, {"error": "请求格式无效"})
            return
        meta["category"] = self._guess_category(meta["url"], meta["title"], meta["description"])
        self._json(200, meta)

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
