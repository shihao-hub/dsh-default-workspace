# tasks-up-to-20261005: 综合任务与实验归整沉淀

> **归整说明**：本项目目录归集了 2026-09-30 至 2026-10-05 期间在 `default-workspace` 根目录下进行的所有独立任务、探索脚本、爬取产物及中间实验数据。

---

## 1. 业务板块与对象职责梳理 (FRAS)

本目录内部共聚合了 7 大核心业务板块，各板块职责与产物如下：

### 板块 1：短视频与音视频下载与转录管线
- **功能职责 (F)**：从抖音、飞书等平台抓取无水印视频、提取音轨并生成字幕与内容摘要。
- **关联对象 (R)**：
  - `douyin-dl/`：本地打包的无水印下载器（配合本机运行环境）；
  - `douyin-333/`, `douyin-av/`, `douyin-dengxiahei/`, `douyin-zhaodao-ziji/`：具体各视频批次的音视频文件与提取物；
  - `lark-video/`, `lark-video-33/`, `xuhuan-video/`：飞书视频与特定主题音视频；
  - `douyin_summary.md`：核心视频提炼内容与分析总结。
- **外部契约 (A)**：依赖本机 `ffmpeg` 音视频解构以及 `faster-whisper` 本地转写能力。
- **约束要求 (S)**：音视频媒体文件（`.mp4`, `.mp3`）体积庞大，仅在本地消费与离线总结，禁止提交至公共 Git 仓库。

### 板块 2：PostgreSQL 内核书籍 OCR 提取与知识结构化
- **功能职责 (F)**：对扫描版《PostgreSQL 数据库内核分析》等技术书籍进行切片裁剪、本地 OCR 识别、提取目录与正文并整理成 Markdown。
- **关联对象 (R)**：
  - `ocr_book.py`, `ocr_batch.py`：批量图像处理与多页 OCR 驱动脚本；
  - `pgkernel_ocr/`, `ocr_out/`：分章节 OCR 识别输出文本；
  - `chapter_map.md`, `toc_draft*.txt`, `ooad_text.txt`：从目录草稿到结构化章节映射的中间演化数据；
  - `ocr_sample_*.jpg`, `ocr_sample_p51.png`, `ocr_test_p101.txt`：测试用切片样本。
- **外部契约 (A)**：依赖本地 OCR 引擎与 PIL / OpenCV 图像预处理。
- **约束要求 (S)**：页码对其与目录层级需要手工对齐校准，避免乱码和断行污染正文。

### 板块 3：Chrome DevTools Protocol (CDP) 浏览器自动化探测
- **功能职责 (F)**：通过 Chrome CDP 调试端口直接与浏览器交互，进行页面探测、DOM 检索、自动化点击与历史记录扫描。
- **关联对象 (R)**：
  - `cdp_probe.py`, `cdp_fetch.py`, `cdp_search.py`, `cdp_click.py`：原子化的 CDP 接口操作脚本；
  - `tmp_scan_chrome_history.py`：扫描 Chrome 访问历史；
  - `probe_title.json`, `click1.json`, `search1.json`, `search2.json`, `needle.txt`：探测结果、DOM 树快照与测试日志。
- **外部契约 (A)**：连接本地 Chrome `--remote-debugging-port`。
- **约束要求 (S)**：测试完成后务必终止测试浏览器进程，避免调试端口被持续占用。

### 板块 4：游戏机制数值与概率分析（饥荒联机版）
- **功能职责 (F)**：计算沃托克斯（Wortox）灵魂偷窃机制、掉落物统计表与概率分析。
- **关联对象 (R)**：
  - `wortox-loot/`：生物掉落物清单与数据模型；
  - `wortox-steal-sheet/`：偷窃收益计算表格与数据整理。
- **外部契约 (A)**：静态数据与本地脚本解析。

### 板块 5：DeepSeek-Harness 客户端定制与主题扩展
- **功能职责 (F)**：探索 DeepSeek-Harness Electron 客户端底层架构，定制 UI 样式与主题。
- **关联对象 (R)**：
  - `.asar-peek/`：客户端 `app.asar` 解包资源探查；
  - `dsh-ext/`, `dsh-ext-root/`：本地扩展接入验证；
  - `dsh-jetbrains-rider-dark-theme.json`：暗色主题配色定义。

### 板块 6：知识整理与专栏摘要
- **功能职责 (F)**：抓取外部文章并进行结构化精读提炼。
- **关联对象 (R)**：
  - `zhihu-article.md`, `zhihu-summary.md`：知乎专栏长文与要点总结；
  - `knowledge-curse-summary.md`：认知盲区“知识的诅咒”分析。

### 板块 7：AI Agent 过程工件与工具集
- **功能职责 (F)**：记录前期规划与设计决策。
- **关联对象 (R)**：
  - `plans/`：历史任务的实施计划；
  - `specs/`：功能设计规格；
  - `research/`：调研日志；
  - `tools/`：临时辅助工具。

---

## 2. 运行与复用指南

1. **环境上下文**：如果需要继续运行本目录下的 Python 脚本（如 `ocr_batch.py` 或 `cdp_*.py`），**执行时必须切换到当前目录**：
   ```powershell
   cd "C:\Users\29580\Documents\deepseek-harness\default-workspace\tasks-up-to-20261005"
   python cdp_probe.py
   ```
2. **不可回写根目录**：后续若对这些历史任务做增补或二次实验，所有新文件必须落在本目录下，不得往父级 `default-workspace` 抛洒任何文件。
