# Mineral 💎

极简书签收藏站，跟随系统浅色/深色主题，支持自动抓取网站信息。

## 功能

- 🔍 搜索 & 分类过滤
- ✨ 添加 URL 时自动获取标题、描述、分类
- ✏️ 编辑 / 删除书签
- 🏷️ 分类自动补全
- 🔒 访问码保护（sessionStorage）
- 📱 响应式布局

## 技术栈

- **前端**: 纯 HTML/CSS/JS，无框架
- **后端**: Python stdlib `http.server`，无依赖
- **存储**: JSON 文件

## 部署

```bash
# 启动 API（默认 127.0.0.1:3721）
python3 api.py

# Nginx 反代 /api/ → localhost:3721
# 静态文件直接 serve index.html
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `MINERAL_TOKEN` | API 认证 token |

## License

MIT

## 持久化运行（当前主机）

`deploy/mineral-api.service` 使用 `OpenClaw` 用户运行，监听 `127.0.0.1:3721`，失败自动重启。
安装前检查主机是否已有同名服务；不要覆盖自定义部署：

```bash
sudo install -m 644 deploy/mineral-api.service /etc/systemd/system/mineral-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now mineral-api.service
```

更新 Python 代码后需 `sudo systemctl restart mineral-api.service`。前端由 Nginx 直接提供，无需构建。

## 标题解析

`POST /api/fetch-meta` 需要与书签写操作相同的访问码。支持 HTTP/HTTPS、自动补 HTTPS、HTML title / Open Graph / Twitter 元数据、字符实体及常见中文编码。
返回 `status: ok` / `title_source: page` 表示真实网页标题；上游 403/503、超时、浏览器验证或缺少标题时，返回 `status: fallback` / `title_source: domain`，同时给出 `warning`，不会编造标题或描述。前端保留手动输入，忽略过期响应，并在标题留空保存时等待解析。

## 回归测试

```bash
python3 -m unittest discover -s tests -v
PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_EXECUTABLE=/path/to/chromium node tests/ui.cjs
```

浏览器测试默认访问线上网站（可通过 `TEST_URL` 覆盖），书签写入由测试拦截，不修改真实收藏。真实上游 503 检查针对本次故障网址；其恢复后需相应调整测试。
