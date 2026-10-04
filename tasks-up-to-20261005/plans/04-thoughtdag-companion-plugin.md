# Plan: dsh-thoughtdag 伴生插件（ThoughtDAG Native Tab Companion）

## 目标描述
- **背景**：此前通过直接修改 `dsh-thoughtdag` 已安装包内的 `lib/client.js`，成功将 ThoughtDAG 顶部的突兀胶囊浮窗改造为会话顶部的原生「思维图」tab（经 `conversation.view` 扩展点注入）。但这属于对第三方 npm 包的原地侵入式 patch，一旦后续 `dsh-thoughtdag` 升级，改动将被完全覆盖。
- **问题**：用户希望确认是否可以开发为**伴生插件（Companion Plugin）**，摆脱对第三方插件源码的修改，并制定完整实施计划。
- **结论**：**完全可行**，且是 DSH 架构下最推荐的解耦形态。
- **目标**：在 `dsh-local-plugins` 本地模组仓库中新建独立的伴生插件 `@local/thoughtdag-companion`，并还原 `dsh-thoughtdag` 的原生代码。
  1. 通过伴生插件的 CSS 强规则彻底消除 ThoughtDAG 原生浮动胶囊与标题栏（无视觉闪烁、无 DOM 竞态）。
  2. 通过伴生插件注册原生 `conversation.view` 扩展点，挂载并纳管 ThoughtDAG 画布 DOM。
  3. 画布内部点击「对话」返回时，通过 postMessage 监听无缝切回 `chat`。
  4. 恢复 `dsh-thoughtdag` 为 0 修改的纯净上游状态，使其后续版本升级完全无痛。

## 需要用户审阅

> [!IMPORTANT]
> **伴生插件方案 100% 可行且架构更加优雅**：
> 1. DSH 的 Client 侧插件运行在同一个单页 DOM 与 Window 执行上下文中，伴生插件与 `dsh-thoughtdag` 完全共享 DOM、Cordis 服务（`slots` / `uiConversation` / `sessions`）及 iframe 跨窗口 postMessage 协议。
> 2. 原版 `dsh-thoughtdag` 只需要保持在后台正常运行并提供 SPA 服务与宿主 API，伴生插件负责外观拦截与 Slot 投影，二者职责解耦。
> 3. 伴生插件开发完成后，原本被 hack 的 `dsh-thoughtdag/lib/client.js` 可以立刻还原回官方干净备份，后续无论官方怎么更新版本，伴生插件都保持独立生效。

> [!WARNING]
> **桌面端热更新与缓存注意**：
> DSH 桌面端对 client bundle 的打包缓存依据是安装清单。在配置软链和 profile 声明后，需通过用户常规的重启桌面应用或浏览器强刷生效。

## 待澄清问题

> [!NOTE]
> 目前技术链路已经完全闭环，无阻塞性待澄清问题。伴生插件命名暂定为 `@local/thoughtdag-companion`（位于 `dsh-local-plugins/thoughtdag-companion`），符合仓库现有的 `@local/*` 命名规范。

---

## 变更方案

变更分为 3 个部分：
1. **新建伴生插件**：在 `dsh-local-plugins/thoughtdag-companion` 下建立标准 DSH 插件结构。
2. **Profile 接入与索引**：在 `~/.dsh/profiles/desktop` 声明依赖并建立 Junction 软链，更新 `dsh-local-plugins/README.md`。
3. **上游插件还原**：将 `dsh-thoughtdag/lib/client.js` 从备份文件还原，验证 upstream 纯净性。

---

### [组件 1：伴生插件 @local/thoughtdag-companion]

#### [NEW] `dsh-local-plugins/thoughtdag-companion/package.json`
声明插件元数据、Cordis 补丁路径及 Client 侧注入项：
```json
{
  "name": "@local/thoughtdag-companion",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "description": "Companion mod for dsh-thoughtdag: suppresses the floating pill and embeds ThoughtDAG into native conversation.view tab.",
  "exports": {
    ".": "./index.js",
    "./client": "./client.js",
    "./package.json": "./package.json"
  },
  "files": [
    "index.js",
    "client.js",
    "cordis.patch.yml"
  ],
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    },
    "client": {
      "platform": "web",
      "immediately": true,
      "inject": [
        "slots",
        "uiConversation",
        "sessions"
      ]
    }
  }
}
```

#### [NEW] `dsh-local-plugins/thoughtdag-companion/index.js`
宿主环境桩模块（仅供 Cordis loader 解析）：
```javascript
/**
 * Host half of thoughtdag-companion bundle.
 */
export function apply() {}
```

#### [NEW] `dsh-local-plugins/thoughtdag-companion/cordis.patch.yml`
向 Cordis profile 注入插件自身：
```yaml
- insert:
    - id: thoughtdag-companion
      name: '@local/thoughtdag-companion'
```

#### [NEW] `dsh-local-plugins/thoughtdag-companion/client.js`
浏览器端逻辑：
1. 注入 CSS 规则：强隐藏 `.dsh-td-switch` 和 `.dsh-td-bar`，定义 `.dsh-td-view` 和 `.dsh-td-embedded` 样式。
2. 注册 `conversation.view` 扩展点（id: `thoughtdag`, order: 20, label: `思维图`）。
3. `MapView` 组件生命周期：
   - `mount`: 从 DOM 捕获 ThoughtDAG 的 `.dsh-td-overlay`，移入 tab 容器，设置 `overlay.hidden = false` 并添加 `.dsh-td-embedded`；若 iframe 尚未加载则赋予 `data-src`；同步当前会话上下文。
   - `unmount`: 将 `.dsh-td-overlay` 放回 `document.body` 并设置 `overlay.hidden = true`，保持 SPA 状态不丢。
4. 监听 `window` 的 `message` 事件：捕获 ThoughtDAG 的 `td:close`，触发 `ctx.uiConversation.binding(sessionId).activate('chat')`。

核心代码实现框架：
```javascript
window.__ModuleLoader__.load({
  id: '@local/thoughtdag-companion',
  factory: require => {
    const React = require('react')
    const module = { exports: {} }
    module.exports.inject = ['slots', 'uiConversation', 'sessions']
    module.exports.apply = ctx => {
      // 1. 注入强样式：彻底隐藏浮动胶囊与 macOS 标题条，提供 embedded 定位
      const style = document.createElement('style')
      style.textContent = `
        .dsh-td-switch, .dsh-td-bar { display: none !important; }
        .dsh-td-view { position: relative; flex: 1; min-height: 0; height: 100%; width: 100%; }
        .dsh-td-overlay.dsh-td-embedded { position: absolute; inset: 0; z-index: 1; }
      `
      document.head.append(style)

      const getSession = () => {
        try {
          const snapshot = ctx.sessions?.list?.getSnapshot?.()
          const id = snapshot?.current
          if (!id) return null
          const session = snapshot.byId?.[id]
          return session ? { id, title: session.displayTitle ?? null, cwd: session.cwd ?? null } : null
        } catch { return null }
      }

      const syncSession = frame => {
        const session = getSession()
        frame?.contentWindow?.postMessage({ source: 'dsh-thoughtdag', type: 'td:current-session', session }, location.origin)
      }

      // 2. 注册原生 conversation.view tab
      if (ctx.slots?.inject) {
        const MapView = () => {
          const containerRef = React.useRef(null)
          React.useEffect(() => {
            const container = containerRef.current
            if (!container) return

            const acquireOverlay = () => {
              const overlay = document.querySelector('.dsh-td-overlay')
              if (!overlay) return null
              const frame = overlay.querySelector('iframe')
              overlay.classList.add('dsh-td-embedded')
              container.appendChild(overlay)
              overlay.hidden = false
              if (frame && !frame.src) {
                frame.src = frame.dataset.src || '/thoughtdag/'
              }
              syncSession(frame)
              const timer = setTimeout(() => syncSession(frame), 300)
              return () => {
                clearTimeout(timer)
                overlay.hidden = true
                document.body.appendChild(overlay)
              }
            }

            let cleanup = acquireOverlay()
            if (!cleanup) {
              const timer = setInterval(() => {
                cleanup = acquireOverlay()
                if (cleanup) clearInterval(timer)
              }, 100)
              return () => {
                clearInterval(timer)
                cleanup?.()
              }
            }
            return cleanup
          }, [])

          return React.createElement('div', { ref: containerRef, className: 'dsh-td-view' })
        }

        ctx.slots.inject('conversation.view', () => ctx.slots.register({
          name: 'conversation.view',
          id: 'thoughtdag',
          order: 20,
          label: () => '思维图'
        }, MapView))
      }

      // 3. 监听画布内部返回对话事件
      window.addEventListener('message', event => {
        if (event.origin !== location.origin || event.data?.source !== 'dsh-thoughtdag') return
        if (event.data.type === 'td:close') {
          const session = getSession()
          if (session?.id && ctx.uiConversation?.binding) {
            ctx.uiConversation.binding(session.id)?.activate?.('chat')
          }
        }
      })
    }
    return module.exports
  }
})
```

---

### [组件 2：DSH Profile 接入与仓库管理]

#### [MODIFY] `~/.dsh/profiles/desktop/package.json`
在 `dependencies` 中挂载：
```json
"@local/thoughtdag-companion": "link:C:/Users/29580/Documents/deepseek-harness/default-workspace/dsh-local-plugins/thoughtdag-companion"
```
并在 `dsh.profile.bundles` 中引入：
```json
"@local/thoughtdag-companion"
```

#### [NEW] Junction 软链接
在 `~/.dsh/profiles/desktop/node_modules/@local/thoughtdag-companion` 创建指向 `default-workspace/dsh-local-plugins/thoughtdag-companion` 的 Junction。

#### [MODIFY] `dsh-local-plugins/README.md`
在本地模组索引表中登记 `@local/thoughtdag-companion` 及其职责。

---

### [组件 3：dsh-thoughtdag 源码还原]

#### [MODIFY] `~/.dsh/profiles/desktop/node_modules/dsh-thoughtdag/lib/client.js`
将原本修改过的 `client.js` 彻底覆盖还原为备份 `client.js.bak-0.5.15` 的内容。
- 确保 `dsh-thoughtdag` 恢复 100% 官方代码。
- 语法校验 `node --check` 必须为 exit code 0。

---

## 验证方案

### 自动化测试
1. **Node 语法与格式检查**：
   ```powershell
   node --check "C:\Users\29580\Documents\deepseek-harness\default-workspace\dsh-local-plugins\thoughtdag-companion\client.js"
   node --check "C:\Users\29580\.dsh\profiles\desktop\node_modules\dsh-thoughtdag\lib\client.js"
   ```
2. **Junction 软链有效性验证**：
   ```powershell
   Get-Item "C:\Users\29580\.dsh\profiles\desktop\node_modules\@local\thoughtdag-companion"
   ```
3. **Profile 语法与依赖树核验**：
   ```powershell
   node -e "const pkg = JSON.parse(require('fs').readFileSync('C:/Users/29580/.dsh/profiles/desktop/package.json', 'utf8')); console.log(pkg.name)"
   ```

### 人工验证
1. 用户重启 DeepSeek Harness 应用（可通过 `@local/app-restart` 插件或手动重启）。
2. 打开任意会话，确认：
   - 顶部不再出现任何「对话 | 思维图」悬浮胶囊。
   - 会话头部「对话 / 轨迹」右侧正常出现「思维图」原生 tab。
3. 点击「思维图」tab：
   - ThoughtDAG 画布正常渲染，会话图与节点正确加载。
4. 在画布内点击「对话」按钮：
   - 界面平滑切回「对话」tab，无报错。
5. 切换会话再切回，画布依然可用。
