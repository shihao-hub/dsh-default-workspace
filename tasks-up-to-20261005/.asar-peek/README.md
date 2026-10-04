# `.asar-peek` — 从 DeepSeek Harness 的 `app.asar` 中提取只读证据

本目录是**研究用临时工作区**，不是产品代码。用途：DSH 桌面版的实现代码打包在
`D:\Users\29580\AppData\Local\Programs\DeepSeek Harness\resources\app.asar`
（121 MB 的 Electron asar 归档）里，DSH 自己的 `read`/`glob`/`grep` 工具读不进去
（`read` 在 asar 上会抛 `Cannot mix BigInt and other types`，`rg` 直接报 os error 3），
所以这里用脚本把需要的包原样解出来，供普通工具阅读与引用。

## 文件

| 文件 | 说明 |
|---|---|
| `extract-asar.mjs` | asar 解析/提取器（Node）。按 pickle 头 + JSON 目录树定位文件，只读，不改动原归档。 |
| `Extract-Asar.ps1` | 同一逻辑的 PowerShell 版本（本机是 Windows PowerShell 5.1，`ConvertFrom-Json -AsHashtable` 不可用，故以 Node 版为准）。 |
| `out/` | 提取结果，保持归档内的目录结构。 |

## 用法

```powershell
# 列出匹配项（不改盘）
$env:LIST_ONLY='1'; node extract-asar.mjs <app.asar> <outDir> '*@deepseek-ai/dsh-tool-web/*'

# 提取
node extract-asar.mjs <app.asar> <outDir> '*@deepseek-ai/dsh-tool-web/*' '*@deepseek-ai/dsh-web/*'
```

`app.asar` 的结构是：偏移 0 起 8 字节 pickle 长度头 → 头部 pickle（其内 4 字节 JSON 长度 + JSON）→
文件数据区从 `8 + headerSize` 开始，JSON 里每个文件带 `offset`（相对数据区）与 `size`。

## 已提取的包

版本均为 `0.2.0-rc.2`，位于 `out/dsh/node_modules/@deepseek-ai/`：

- `dsh-tool-web` — 面向模型的 `web_search` / `web_fetch` 工具（`lib/index.js`）
- `dsh-web-search-deepseek` — `deepseek-official` 搜索提供方（含真实 endpoint 与鉴权）
- `dsh-web-fetch-http` — 匿名 HTTP(S) 抓取提供方
- `dsh-web` — `ctx.web` 能力 seam（提供方选择 + 结果封顶）
- `dsh-client-ui-settings-web-search` — Web 搜索设置页

## 注意

- `out/` 只是**阅读副本**，运行时加载的仍是 `app.asar` 内的那份；两者内容一致（逐字节提取）。
- 归档内的真实路径是 `dsh/node_modules/@deepseek-ai/<pkg>/...`，引用时建议写归档路径 + 行号。
- 若 DSH 升级，`out/` 会过期，需用上面的命令重新提取。
