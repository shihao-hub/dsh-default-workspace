# Bug Fix Document

## Summary
DeepSeek Harness 启动时因无法激活 `@local/skills-panel` 与 `@local/traj-translate-v4` 两个本地插件而崩溃弹窗（web boot: 2 entries did not activate）。

## Reproduction
1. 正常启动 DeepSeek Harness 桌面客户端（加载本地已安装插件 `@local/skills-panel` 和 `@local/traj-translate-v4`）。
2. Web boot 阶段加载插件 bundle 时报错并弹出崩溃恢复窗口：
   - 报错信息提示 `@local/skills-panel: import failed (see console for the import error)`
   - 报错信息提示 `@local/traj-translate-v4: import failed: ... loaded without registering "@local/traj-translate-v4" via __ModuleLoader__.load`
   - 控制台出现 `Uncaught TypeError: Cannot read properties of undefined (reading 'endsWith')` 以及 `duplicate factory registration for "@local/traj-translate"`。

## Root Cause
经检查 `@deepseek-ai/dsh-client-modules` 的客户端模块加载机制与两个插件源码，定位根因如下：

1. **`@local/skills-panel` 缺失 `id`**：
   - 在 `skills-panel/client.js` 中调用 `window.__ModuleLoader__.load({ meta: {}, factory: ... })` 时，入参对象未提供 `id: '@local/skills-panel'`。
   - `dsh-client-modules` 执行 `register(registration)` 时执行 `const ownerId = stripClientSuffix(registration.id)`，由于 `registration.id` 为 `undefined`，调用 `undefined.endsWith("/client")` 立即抛出 `TypeError: Cannot read properties of undefined (reading 'endsWith')`。这导致整个插件组合 bundle 解析失败。

2. **`@local/traj-translate` 注册 ID 与包名不一致**：
   - `traj-translate/package.json` 及 `cordis.patch.yml` 中声明的插件包名为 `@local/traj-translate-v4`。
   - 但 `traj-translate/client.js` 中注册时写为 `id: '@local/traj-translate'`（缺失 `-v4` 后缀）。
   - Harness 的 client-modules 在等待 `@local/traj-translate-v4` 到达时，未能找到同名工厂函数注册，并在后续触发重复加载检查时报出 `duplicate factory registration for "@local/traj-translate"` 与 `loaded without registering "@local/traj-translate-v4" via __ModuleLoader__.load`。

## Impact
- DeepSeek Harness 桌面端启动中断，无法正常进入主界面。
- 用户侧两个插件均未被成功激活。

## Fix Acceptance Criteria
### AC-1
- WHEN DeepSeek Harness 客户端加载 `skills-panel/client.js` 时；
- `window.__ModuleLoader__.load` 传入正确的 `id: '@local/skills-panel'`，`stripClientSuffix` 能够正常提取包名，不再抛出 `Cannot read properties of undefined (reading 'endsWith')`。

### AC-2
- WHEN DeepSeek Harness 客户端加载 `traj-translate/client.js` 时；
- `window.__ModuleLoader__.load` 传入的 `id` 与 `package.json` 中的包名 `@local/traj-translate-v4` 保持严格一致，client-modules 能够成功识别并注册 `@local/traj-translate-v4`。

### AC-3
- WHEN Harness 进行 web boot 阶段插件初始化；
- 两个插件模块均能被 client-modules 成功解析与导入，不再报 `web boot: 2 entries did not activate`。

## Fix Approach
改动非常集中且目标明确（仅需修改 2 个生产文件）：

1. **修改 `skills-panel/client.js`**：
   - 在 `window.__ModuleLoader__.load({...})` 的入参配置对象中，补充 `id: '@local/skills-panel'`。
2. **修改 `traj-translate/client.js`**：
   - 将 `window.__ModuleLoader__.load({...})` 的 `id` 从 `'@local/traj-translate'` 修正为 `'@local/traj-translate-v4'`。

## Tasks
- [x] 1. 为 `skills-panel/client.js` 补齐模块注册 ID
  - Files: `skills-panel/client.js`
  - 实现细节：在 `window.__ModuleLoader__.load` 调用对象中增加 `id: '@local/skills-panel'`。
  - Verify: 检查 `skills-panel/client.js` 中 `__ModuleLoader__.load` 包含 `id: '@local/skills-panel'`
  - Ref: AC-1
- [x] 2. 修正 `traj-translate/client.js` 模块注册 ID 与包名一致
  - Files: `traj-translate/client.js`
  - 实现细节：将 `id: '@local/traj-translate'` 修改为 `id: '@local/traj-translate-v4'`。
  - Verify: 检查 `traj-translate/client.js` 中 `__ModuleLoader__.load` 的 `id` 为 `'@local/traj-translate-v4'`
  - Ref: AC-2, AC-3
