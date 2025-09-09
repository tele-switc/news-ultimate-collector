# 外刊聚合 · 科技精选（OpenAI 风格）

- 每天 08:00（北京时间）自动抓取：主流科技/新闻媒体（RSS 多频道 + Sitemap 兜底）+ GitHub 仓库（许可证白名单才全文导入）
- 站点：小卡片、大圆角、圆形黑色简约按钮，卡片点开阅读器，显示原始标题/作者/发布时间

## GitHub 仓库来源（你指定）
- plsy1/emagzines
- hehonghui/awesome-english-ebooks  
说明：仅当仓库 LICENSE 为允许再分发（MIT/Apache/BSD/CC BY/CC0 等）时，才会“全文导入”；否则仅保留元数据并跳转到 GitHub 原页。

## 一步部署（零配置）
1. 新建仓库
   - GitHub → New → 取名（如 `news-portal-tech`）→ Create repository
2. 上传代码
   - 进入仓库 → Add file → Upload files → 上传本项目所有文件（保持目录结构）
3. 开启 Pages
   - Settings → Pages → Build and deployment → Source: Deploy from a branch
   - Branch: `main` / Folder: `/docs` → Save（等待几十秒，会出现站点 URL）
4. 回填（建议先跑一次）
   - Actions → Backfill (Sitemap + local fulltext) → Run workflow（默认从 2025-01-01 到今天）
5. 每日定时
   - Daily fetch 将在北京时间 08:00/08:10/08:20/08:30 自动运行

## 目录结构
- scripts/ 抓取与解析逻辑（含 GitHub 仓库连接器、全文解析器）
- docs/ 静态站点（GitHub Pages 直出）
- .github/workflows/ Actions 工作流（定时抓取、回填）

## 合规
- 遵守 robots.txt 与站点条款，不绕过付费墙/登录。
- GitHub 仓库导入模块会检查仓库许可证，仅在允许再分发的许可证下导入全文；否则仅保留元数据与跳转链接。
