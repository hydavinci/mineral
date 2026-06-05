# Mineral 💎

极简书签收藏站，暗色系设计，支持自动抓取网站信息。

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
