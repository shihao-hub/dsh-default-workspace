# DSH 技能（Skill）能否不重启就重新加载 —— 源码调查报告

- 调查对象：DeepSeek Harness 桌面版自带运行时，版本 `0.2.0-rc.2`（build commit `04f392c9`，见 asar 根 `package.json`）。
- 一手来源：`app.asar` 解包目录（`C:\Users\29580\AppData\Local\Temp\dsh-asar-src\dsh\`，即 asar 内 `dsh\` 的完整镜像）。本报告所有引用路径均相对该 `dsh\` 根，格式 `相对路径:行号`。调查过程在工作区另留有逐包抽取副本 `dsh-ext\`，与解包目录逐字节一致（已对关键文件做 SHA256 比对）。
- 调查时间：2026-02（本会话）。

---

## 结论（TL;DR）

**可以。技能系统天生就是热重载设计，改技能文件不需要重启应用、不需要重开会话。** 具体分两层：

| 层面 | 结论 |
|---|---|
| Agent 会话层（`available_skills` 目录 + `skill` 工具） | **完全热更新。** ① 目录清单不是会话启动时固定的，而是在**每个模型步骤前**重新快照、按内容摘要（SHA256）比对，变化就以「替换目录」系统提醒的形式重发（`dsh-tool-skill/lib/index.js:203-236,262-286`）——**触发点 = 该会话自身的下一个模型步骤，各会话独立比对、互不推送**（实测确认见第 8 节）；② `skill` 工具每次调用都**实时从磁盘读 SKILL.md 正文**，正文编辑连缓存失效都不需要（`dsh-skill-filesystem/lib/index.js:115-134`，README 明言「每次加载都会重新读取当前文件」）。 |
| 宿主/插件层（`skills/list` API） | **热更新，但靠拉取不靠推送。** 每次调用走到注册表 `list()`；注册表只有一层**内存**候选缓存（无 TTL、不落数据库），文件 watcher 一触发就整体作废，下一次调用即重新扫描磁盘（`dsh-skill/lib/index.js:265-297,376-380`）。skills-panel 这类客户端插件**只需重新调用 `skills/list`**，无需重启应用或会话；但宿主不会把技能变更推送到 UI，面板要自己刷新（轮询或打开时拉取）。 |

磁盘 watcher（chokidar，深度 1）**默认开启**（`watch: true`），新增/删除/改名/编辑 frontmatter 通常在约 0.3 秒内触发失效；宿主自己的 `write`/`edit` 工具改动走同步失效通道，连 watcher 都不用等。

**仍需重启宿主的只有**：改组合/插件配置（`cordis.patch.yml` 各层只在启动时读取）、改环境变量（`DSH_HOME` / `DSH_AGENTS_HOME` 等）、升级应用。

---

## 证据

### 1. `available_skills` 目录在什么时机构建？

**结论：不是启动时一次性构建，也不缓存在数据库里；它在每个模型步骤（pre-step）重新计算，并以持久化会话消息的形式「就地替换」。**

技能目录并不是系统提示词（system prompt）的一部分，而是一条带 `<system-reminder>` 的用户消息，`source.kind = "skill-catalog"`，持久化在会话事件流里：

- `node_modules/@deepseek-ai/dsh-tool-skill/lib/index.js:238-261`（`renderCatalogMessage`）：

  ```js
  text: [
    "<system-reminder>",
    "A skill is a reusable set of task-specific instructions. ...",
    "<available_skills>",
    ...renderCatalogEntries(entries),
    "</available_skills>",
    ...
  ].join("\n")
  ```

- **每个模型步骤都重新快照**：`dsh-tool-skill/lib/index.js:203-236` 注册了第二个 `agent/pre-step` 监听器，每次模型请求前执行 `await ctx.skills.snapshot({ cwd, signal, scope: agent })`（:207-214），对目录条目算 SHA256 摘要（`digestCatalogEntries`，:301-304），与会话历史里最后一次已发布目录的摘要比对（`catalogHistory`，:331-348）；不一致就用**替换式**目录更新：

  - `dsh-tool-skill/lib/index.js:231`：`const catalog = history.published ? renderCatalogUpdate(entries) : renderCatalogMessage(entries);`
  - `dsh-tool-skill/lib/index.js:269`（`renderCatalogUpdate` 正文）：

    ```
    "The available skill catalog changed. This complete catalog replaces every
    earlier available-skills list in this session:"
    ```

- 摘要只取决于条目（名称+描述）列表，**正文编辑不改变摘要、也就不重发目录**——因为正文本来就是实时读的（见第 3 节）。包文档对此有明确说明：`node_modules/@deepseek-ai/dsh-skill-filesystem/README.zh.md:139`「仅涉及正文的编辑不会改变目录 digest」。
- 首个步骤发布初始目录；会话恢复/fork 后，`catalogHistory` 会扫描已有会话事件找到旧目录，之后的更新自动走「替换」形态（`dsh-tool-skill/lib/index.js:331-348`）。

### 2. 技能从哪些目录发现（优先级）？

**结论：6 档 rank，与 skills-panel 设计文档 2.1 节一致。**

- 代码：`node_modules/@deepseek-ai/dsh-skill-filesystem/lib/index.js:21-28`（rank 常量）、`:150-188`（`roots()`）。
- 官方表：`node_modules/@deepseek-ai/dsh-skill-filesystem/README.zh.md:48-56`：

  | Rank | 来源 | 路径 |
  |---|---|---|
  | 100 | `project-dsh` | `<projectRoot>/.dsh/skills` |
  | 200 | `project-agents` | `<projectRoot>/.agents/skills` |
  | 300 | `custom` | `Config.customSkillDirs` |
  | 400 | `user-dsh` | `<dshHome>/skills`（即 `~/.dsh/skills`） |
  | 500 | `user-agents` | `<agentsHome>/skills`（即 `~/.agents/skills`） |
  | 600 | `bundled` | `bundledSkillDir` 配置或 `$DSH_BUNDLED_SKILL_DIR` |

- 项目根 = 最近的含 `.git` 的祖先目录，找不到就用 cwd（`dsh-skill-filesystem/lib/index.js:807-815`）。
- `agentsHome` 解析：`config.agentsHome ?? process.env.DSH_AGENTS_HOME ?? ~/.agents`（`:78`）；`dshHome` 经 `resolveDshHome`：显式配置 > `$DSH_HOME` > `~/.dsh`（`node_modules/@deepseek-ai/dsh-home-paths/lib/index.js:73-76`）。
- 桌面版实际组合：基础 bundle 挂载 `dsh-skill` + `dsh-skill-filesystem` + `dsh-tool-skill`（`node_modules/@deepseek-ai/dsh-base/cordis.patch.yml:294-305`，另挂 `skill-badge` 但 `disabled: true`）。Web 预设还会把随包技能目录塞进 `customSkillDirs`（`node_modules/@deepseek-ai/dsh-web-app/presets/cordis.patch.yml:143-148`）。
- 另有不走磁盘的内置 provider：`dsh-office`（office-docx/pptx/xlsx，`node_modules/@deepseek-ai/dsh-skill-office/lib/index.js:54-96`）与 `dsh-badge`（`node_modules/@deepseek-ai/dsh-skill-badge/lib/index.js:29-43`），以及运行时注册的 runtime 技能（rank 250，`node_modules/@deepseek-ai/dsh-skill/lib/index.js:20-21`）。
- 重名裁决：rank 小者优先，同层内按 provider 注册序；被覆盖者告警丢弃（`dsh-skill/lib/index.js:312-330,519-521`）。

### 3. `skill` 工具调用时，SKILL.md 是实时读还是缓存快照？

**结论：实时读磁盘，零内容缓存。**

- 工具 `execute`：先 `ctx.skills.list()` 校验名字，再 `ctx.skills.get()` 取全文（`node_modules/@deepseek-ai/dsh-tool-skill/lib/index.js:138-157`）。
- 注册表 `get()` 把候选交回 provider：`match.provider.get(match.candidate, options)`（`node_modules/@deepseek-ai/dsh-skill/lib/index.js:250-264`）。
- 文件系统 provider 的 `get()` → `parseSkillFile` → `readSkillText` → `fs.readText`/`readFile`，每次调用都重新打开文件（`node_modules/@deepseek-ai/dsh-skill-filesystem/lib/index.js:115-134,664-705,709-759`）。
- 官方文档一锤定音：`node_modules/@deepseek-ai/dsh-skill-filesystem/README.zh.md:42`「目录与正文具有独立的生命周期：……**每次加载都会重新读取当前文件，因此编辑 skill 正文无需版本化或缓存失效**」；`:152`「无正文修订协议——已加载正文是普通的已保留工具历史；后续文件编辑会影响后续调用，但既不会改写旧结果」。
- 内置 provider 同样每次调用重读文件（badge：`dsh-skill-badge/lib/index.js:40`；office：`dsh-skill-office/lib/index.js:85-88`），但注意 office/badge 的**描述元数据**是插件 `apply()` 时一次性快照的（office `:59-79` 用 `readFileSync` 构建候选）——改它们的 SKILL.md 描述需要换包/升级才变。

### 4. 是否存在文件 watcher / 热重载机制？

**结论：有，且默认开启。chokidar 深度 1 监视每个技能根目录 + 宿主写操作同步失效 + 缺失根的祖先轮询探测，三通道。**

- 配置默认值：`node_modules/@deepseek-ai/dsh-skill-filesystem/lib/index.js:26-28,37-42`：

  ```js
  const DEFAULT_WATCH_STABILITY_THRESHOLD_MS = 200;
  const DEFAULT_WATCH_POLL_INTERVAL_MS = 100;
  const DEFAULT_WATCH_MAX_PROJECTS = 128;
  ...
  watch: z.boolean().default(true),
  watchUsePolling: z.boolean().default(false),
  ```

- chokidar 句柄：`:371-430`，`depth: 1`、`awaitWriteFinish: { stabilityThreshold: 200, pollInterval: 100 }`、`atomic: true`；相关事件（顶层 `*.md` 增删、`<name>/SKILL.md` 增删改）→ `queueInvalidation()` 微任务批量去重后调 `control.invalidate`（`:412-442,462-471`；相关性判定 `:541-551`）。`references/`、`scripts/` 等资源子树**不**触发（README.zh.md:81、代码 `:546-550` 只认深度 ≤2）。
- 失效语义：注册表 `invalidateCache()` = revision+1、清空全部 collect 缓存、广播 `skills/change`（`node_modules/@deepseek-ai/dsh-skill/lib/index.js:376-380`）；**没有 TTL**，只有 provider 的 `invalidate()` 或运行时注册/注销会清缓存（`node_modules/@deepseek-ai/dsh-skill/README.md:103`）。
- 宿主自身写文件：`fs/observed` 事件里识别 `edit`/`write` 工具，命中受监视路径就**同步**失效，不等 watcher（`dsh-skill-filesystem/lib/index.js:57-60,136-141,239-244,564-568`）。
- 尚不存在的根目录：从最近存在祖先起用 `fs.watchFile` 按 `watchPollIntervalMs` 轮询逐段探测，出现后换 chokidar（`:342-370,502-537`；README.zh.md:151）。
- watcher 启动失败不阻塞发现：该次 `list()` 标记 `complete: false` → **不写缓存** → 每次调用都直接重扫磁盘（`:93-108` + `dsh-skill/lib/index.js:288-294,353-358`），坏的一面变慢，好的一面永不陈旧。
- 项目 watcher 上限 128 个，LRU 逐出并触发一次失效（`:225-237`）。

### 5. 会话中途编辑技能文件，对当前会话是否生效？

**结论：生效，且分两种时效。**

| 改动 | 目录（available_skills） | `skill` 工具读到的正文 | 生效时机 |
|---|---|---|---|
| 新增 / 删除 / 改名技能 | 变（digest 变）→ 重发「替换目录」提醒 | 新技能立即可 `get` | 下一个模型步骤前（watcher 失效后约 0.3s 内 + 一次微任务） |
| 编辑 frontmatter（name/description/whenToUse/invocation） | 变 → 重发 | 变 | 同上 |
| 只编辑 SKILL.md 正文 | **不变**（不重发目录） | 变（实时读） | **下一次 `skill` 调用立即生效** |
| 宿主 `write`/`edit` 工具自己改的 | 同步失效 | 实时 | 本轮内即可 |
| 外部 IDE / git / shell 改的 | chokidar 捕获 | 实时 | 约一个稳定窗口（200ms）之后 |

- 旧目录消息在模型视图里被**就地替换**而非追加（`dsh-tool-skill/lib/index.js:221-235` 按 `message.id` 替换），这是为 KV cache 设计的（README.zh.md:137-139「watcher 触发的失效可促使上述消费方在现有请求历史中追加替换目录」）。
- 已加载进历史的 `<skill_content>` 不会被改写，也不会收到"正文已变"通知（README.zh.md:152）。
- 用户还可以在消息里用 `/skill-name` 手势显式触发加载：pre-step 监听器扫描用户消息文本，实时 `ctx.skills.get()` 后注入 `<skill_content>`（`dsh-tool-skill/lib/index.js:168-202,373-394`）——这也是热数据。

### 6. 相关配置项、环境变量、开关

**环境变量**（无专门的"重载"开关）：

- `DSH_HOME`：Harness 主目录，默认 `~/.dsh`（`node_modules/@deepseek-ai/dsh-home-paths/lib/index.js:15,73-76`）→ 决定 `~/.dsh/skills`（rank 400）。
- `DSH_AGENTS_HOME`：默认 `~/.agents`（`dsh-skill-filesystem/lib/index.js:78`）→ 决定 `~/.agents/skills`（rank 500）。
- `DSH_BUNDLED_SKILL_DIR`：rank 600 随包根（`:84`）；**桌面版 0.2.0-rc.2 里没有任何代码设置它**（已 grep Electron 主入口 `lib/main.js` 与全部包），纯可选。
- `DSH_TELEMETRY_DISABLED` 等与技能无关。

**插件配置**（`@deepseek-ai/dsh-skill-filesystem` 的 Config，`dsh-skill-filesystem/lib/index.js:31-44`；中文配置表见 README.zh.md:67-77）：

- `providerName`（`filesystem`）、`includeDefaultRoots`（`true`）、`dshHome`、`agentsHome`、`customSkillDirs`（`[]`）
- `watch`（`true`）、`watchUsePolling`（`false`）、`watchStabilityThresholdMs`（200）、`watchPollIntervalMs`（100）、`watchMaxProjects`（128）、`watchFollowSymlinks`（`true`）、`bundledSkillDir`

**其他相关 Config**：

- `@deepseek-ai/dsh-skill`：`collectCacheMaxEntries`（128，`dsh-skill/lib/index.js:18,120`）。
- `@deepseek-ai/dsh-tool-skill`：`catalogDescriptionMaxLength`（500，`dsh-tool-skill/lib/index.js:40,49`）。

**组合（composition）覆盖入口**：补丁层顺序为 bundle 层 → profile 的 `cordis.patch.yml` → **`$DSH_HOME/cordis.patch.yml`（机器级用户层，对每个 profile 生效）** → `--patch` 覆盖层（`node_modules/@deepseek-ai/dsh/lib/profile-boot-BZ2ZjNWi.js:110-117,193-198`；`node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1023-1034`，其中 `:1028` 就是 home 层）。桌面宿主以 profile `"desktop"` 启动（`node_modules/@deepseek-ai/dsh-desktop-host/lib/index.js:215-245`），同样吃到 home 层。**这些只在启动时读取**。

**CLI**：未发现技能热重载相关的命令行开关。

### 7. 宿主/插件层：`skills/list` 每次调用是否重扫磁盘？（skills-panel 关心的问题）

**结论：每次调用都经过"内存缓存 → 失效后重扫"的路径；不需要重启应用或会话，重新调用即可拿到最新目录。但宿主不推送变更事件，客户端要自己拉。**

- 线上 API 名就是 `skills/list`：remote id `@deepseek-ai/dsh-api-session-controller#skills/list`、`namespace: "skills"`（`node_modules/@deepseek-ai/dsh-api-remotes/lib/client.js:11742-11744`），由 `ctx.plugin(SessionSkillCatalog)` 注册（`node_modules/@deepseek-ai/dsh-api-session-controller/lib/index.js:2871`）。
- 宿主实现：`node_modules/@deepseek-ai/dsh-api-session-controller/lib/types/skill-catalog.js:91`「Host service backing `ctx.remote.skills` **without activating a cold Agent**」；`list()` 从会话投影取 cwd 与 agentPreset（:120-150），选活动 agent 的 scoped 注册表或全局注册表（:151-157），然后 `skillRegistry.list({ cwd, scope })` 并过滤 `isUserInvocable`（:161）。**没有落盘缓存，也不写数据库。**
- 注册表 `list()` → `collect()`：缓存键为 `{cwd, scopes, revision}` 的**纯内存** Map（上限 128 条），revision 未变则命中，否则全量重扫（`node_modules/@deepseek-ai/dsh-skill/lib/index.js:265-297,395-401`）。watcher 失效会 bump revision，所以「外部改了文件 → 下一次 `skills/list`」一定是新数据。
- `skills/change` 事件只存在于宿主进程内部（`dsh-skill/lib/index.js:402-412`），**没有对应的远端推送事件**——已 grep `dsh-api-remotes` 的 remote-events，无技能相关事件。内置 UI 客户端也只在 `agent-preset/selected` 和 `connection/reset` 时失效自己的目录缓存、其余靠按需拉取（`node_modules/@deepseek-ai/dsh-client-ui-skill/lib/client.js:332-363,429-430`）。
- 对 skills-panel 的直接推论：**界面要看到新技能，只需重新发起一次 `skills/list`**（面板打开/刷新/聚焦时拉取，或低频轮询）；冷会话（应用重启后未激活的会话）也能查——`scopeFor(agentPreset)` 会在不激活 Agent 的情况下解析预设 scope（`skill-catalog.js:186-198`）。

### 8. 实测确认（本机验证）：刷新点是「会话自己的下一个模型步骤」，且按会话独立

实测现象：技能文件改完后，**开着的空闲会话不会有任何变化；发起新轮次才看到目录更新；多个会话各自独立刷新**。与源码完全吻合，机制精确化为三层时效：

| 层 | 状态归属 | 更新时机 |
|---|---|---|
| 宿主注册表（watcher → revision 失效） | 全局共享，即时 | 文件变化后约 0.3s，之后所有读取都拿新数据 |
| 会话目录（`available_skills` 提醒消息） | **每个会话独立** | **仅在该会话下一次模型步骤前**快照+比对（`dsh-tool-skill/lib/index.js:203-236`）；空闲会话永远不主动更新 |
| `skill` 工具正文 | 无状态 | 每次调用实时读盘 |

「按会话独立」的代码依据：比对基准不是任何全局状态，而是**该会话自己事件流里**最后一条已发布目录——`catalogHistory(agent)` 逐条回扫 `agent.session.eventAt(...)` 找 `source.kind === "skill-catalog"` 的历史消息、重算 digest（`dsh-tool-skill/lib/index.js:331-348`）；替换消息也只写入该会话自己的历史。系统里没有跨会话的目录推送通道。

两点精确化：

1. **触发的不是「发消息」这个动作，是「模型步骤」**。`:203` 的 `agent/pre-step` 对每一步执行，同一轮 agent loop 里的每次模型请求都会重快照；只是从用户视角，「发起新轮次」必然产生一次模型步骤，所以实测表现为「新轮次才刷新」。不产生模型请求的动作——打开会话、翻历史、插件调 `skills/list`——都不会让该会话的目录消息更新。
2. **`skills/list` 与会话目录是两条独立数据路径**。`skills/list` 直接读宿主注册表（第 7 节），拿到的永远是全局最新；会话目录消息只由 pre-step 更新。所以完全可能出现「skills-panel 已显示新技能、但某个会话的模型目录还是旧的」——两边数据源和时效都不同。

---

## 实操建议

**A. 日常改技能（不需要任何重启）**

1. 直接编辑/新增文件到任一技能根，例如：
   - `~/.agents/skills/my-skill.md`（rank 500，平铺单文件），或
   - `~/.agents/skills/my-skill/SKILL.md`（目录 bundle，`references/` 等资源放同目录），或
   - 项目内 `<项目根>/.dsh/skills/...`（rank 100，优先级最高）。
2. frontmatter 必须有 `name`（kebab-case）和 `description`；可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`（`dsh-skill-filesystem/lib/index.js:679-704,849-859`；README.zh.md:36-38）。
3. 等 ~0.5 秒（watcher 稳定窗口），然后：
   - 会话里随便发一条消息 → 模型会看到「替换目录」提醒；
   - 或直接在消息里打 `/my-skill` → 立即注入最新内容；
   - 或让模型直接调 `skill` 工具 → 读到的就是最新正文。

**B. skills-panel 插件**

- 面板每次打开 / 获得焦点 / 用户点刷新时调用 `skills/list`（带目标 `sessionId`）；不要在客户端长缓存目录，因为宿主不会推送变更。
- 若想"自动感知"，只能轮询（建议 ≥1–2s 间隔，成本 = 一次进程内快照 + 一次磁盘扫描）；没有可订阅的远端技能变更事件。
- 注意 `skills/list` 只返回 `user-invocable` 的技能；模型目录则只含 `model-invocable`（`skill-catalog.js:161` vs `dsh-tool-skill/lib/index.js:217`），两者可能不同。

**C. 加自定义技能根目录 / 调 watcher（需重启宿主一次）**

在 `%USERPROFILE%\.dsh\cordis.patch.yml`（即 `$DSH_HOME/cordis.patch.yml`）加一层补丁，参照 web 预设的写法（`dsh-web-app/presets/cordis.patch.yml:143-148`）重新声明该插件并给 config，例如 `customSkillDirs`、`watchUsePolling: true`（网络盘/OneDrive 等原生 watch 不可靠的场景）。改完需重启应用（补丁只在 boot 时组合，见 `profile-boot-BZ2ZjNWi.js:193-198`）。⚠️ 补丁行与基础组合同 id（`skill-filesystem`）时的合并/覆盖语义本次未在 loader 源码里逐行验证，动手前建议先小规模验证。

**D. 想强制立即刷新（绕过 watcher 的保险手段）**

让模型用 `write`/`edit` 工具碰一下技能文件（哪怕内容不变的重写）——`fs/observed` 会同步失效缓存，不依赖 chokidar（`dsh-skill-filesystem/lib/index.js:57-60`）。

---

## 局限与不确定点

1. **watcher 只看两层**：`<root>/<name>.md` 与 `<root>/<name>/SKILL.md`；更深层的 `references/`、`scripts/`、`assets/` 变更不触发目录失效（`:541-551`，README.zh.md:81/114/148）。资源文件本来也是运行时按路径现读的，一般无碍，但"新增资源文件"不会让模型目录变化。
2. **正文修订不回溯**：已进入会话历史的 `<skill_content>` 不会被改写或标记过期（README.zh.md:152）；模型如果引用的是旧加载内容，需要重新调一次 `skill`。
3. **watcher 失败的静默降级**：chokidar 起不来（权限/网络盘）时只有一条 warn 日志，发现标记为不完整、不缓存，每次调用重扫（`dsh-skill-filesystem/lib/index.js:96-107,324-330`）——功能仍热，但性能退化为逐次扫描；排障时可搜日志前缀 `skill-filesystem:`。
4. **office/badge 内置技能的描述是启动期快照**（`dsh-skill-office/lib/index.js:59-79`），只有正文是热读；它们位于安装目录/asar 内，用户正常不该改。
5. **`DSH_BUNDLED_SKILL_DIR` 在本发布中无设置方**：rank 600 的"随包根"目前是给内嵌部署预留的通道；桌面版随包技能（office 三件套）走的是独立 provider，预设技能目录在 web 预设里走 `customSkillDirs`。桌面组合里随包 kebab 技能（如 `cordis-plugin-development`）是否出现取决于所选 profile 的补丁栈，未逐层展开验证。
6. **`skills/change` 无远端推送**基于对 `dsh-api-remotes` 事件目录的 grep（无技能事件）；若未来版本加了推送通道，B 节结论需复核。
7. **版本局限**：以上全部结论基于 `0.2.0-rc.2`（asar 解包）。升级后行号会漂移，但该子系统近期的演进方向（watch + 每步快照 + 实时读）是文档化的产品行为，短期大概率稳定。
8. 本次未发现任何"重载技能"的命令/CLI/斜杠命令；如果用户想要的是"手动触发重载"按钮，现版本没有，等价物是 `skills/list` 重查（宿主层）或下一条消息（会话层）。
