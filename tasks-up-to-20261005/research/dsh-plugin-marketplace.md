# DeepSeek Harness 有插件市场吗？

> 调研日期：本机 DSH 版本 **0.2.0-rc.2**（desktop profile）
> 结论一句话：**官方没有插件市场，只有"插件管理"（plugin manager）。** 官方指定的发现渠道是 GitHub 的 `dsh-plugin` topic；"市场"这个概念完全由第三方社区包提供。

---

## 一、结论（Bottom line）

| 问题 | 答案 |
|---|---|
| DSH 内置官方插件市场？ | **否**。DSH 自身代码里不存在市场概念——既没有目录/索引服务，也没有搜索、评分、榜单页面。 |
| 官方怎么说插件发现？ | **用 GitHub topic**。官方 README：「Add the [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic to your plugin repository for discoverability.」 |
| DSH 有插件系统吗？ | **有，而且很开放**。插件 = 装进 profile 的 npm 包（pnpm 依赖），装完挂到 Cordis 配置树上。 |
| 有"插件管理"界面吗？ | **有**。Web/桌面侧栏的**插件**入口（`ui-plugin-manager`），是一个管理页，不是市场页。 |
| 官方打算做市场吗？ | **没有表态，也没有承诺**。社区有人提了正式提案（Discussion #1825），但**零官方回复**；全仓库 discussion 标题搜 `marketplace` 命中 **0**。 |
| 那"插件市场"是哪来的？ | **第三方**。社区在 npm 上发布了一批名为 `*marketplace*` / `dshmarket` 的插件，**热插进 DSH** 来补上市场功能。 |

### 官方口径原文（最硬的三条）

1. **官方 README**（`deepseek-ai/deepseek-harness`，master 分支）在 "Community and support" 一节点名了插件发现方式：

   > Add the [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic to your plugin repository for discoverability.

   即：**发现 = 给仓库打 GitHub topic**。这与 `dsh-plugin-marketplace`、`dsh-find-plugin` 等第三方包"去扫 GitHub topic"的做法完全对应——它们扫的正是官方指定的那个 topic。

2. **官方 CONTRIBUTING.md** 明确"仓库不是命令"：

   > We do not believe that packages in the official repository are inherently more important than packages created by the community. You may consider this repository an idea, an official showcase, and a source of inspiration, but not a mandate from us.

   同一文件还写明：**目前不接受外部 PR**（"we cannot accept external pull requests at the moment"），只能通过 Discussions 反馈。这解释了为什么社区的市场提案只能停在 discussion 里。

3. **官方 README 列出的社区渠道是 Discussions 与 Discord**，没有任何官方市场站点：

   > - Submit feedback or bug reports through [GitHub Discussions](...).
   > - Add the [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic to your plugin repository for discoverability.
   > - Join [DeepSeek Harness Discord community](https://discord.gg/4MrtZUhpxg).

   即官方给出的三条社区路径里，**唯一与"发现插件"有关的就是那个 GitHub topic**。

**最关键的证据**：在 DSH 的发行产物 `app.asar` 里全文搜索中文关键词——

```
插件市场   → 0 处
市场       → 0 处
插件管理   → 27 处
```

DSH 内部有"插件管理"这个词，**从来没有"插件市场"这个词**。全仓库（含所有随包 README）搜到的 14 处 `marketplace` 全部是第三方依赖的文档残留，与 DSH 功能无关：

- `marketplace_purchase` 系列 → `@octokit/webhooks` 的 GitHub Marketplace webhook 事件表
- `Visual Studio Marketplace` → `@sinclair/typebox` 文档里的 VS Code 语法高亮插件地址

> 证据：`D:\Users\29580\AppData\Local\Programs\DeepSeek Harness\resources\app.asar`（121 MB，Electron asar，DSH 实现与全部 README 一并打包在内）。搜索方式为对 asar 原始字节做 UTF-8 正则匹配。

---

## 二、DSH 真实的插件机制

### 2.1 插件就是 npm 依赖，装在 profile 目录里

profile 目录 `$DSH_HOME/profiles/<name>/` 就是一个小 npm 工程。本机 `desktop` profile 实测：

`C:\Users\29580\.dsh\profiles\desktop\package.json`

```json
{
  "dependencies": {
    "@local/skills-panel": "link:C:/Users/29580/Documents/deepseek-harness/default-workspace/skills-panel",
    "@local/traj-translate-v4": "link:C:/Users/29580/Documents/deepseek-harness/default-workspace/traj-translate",
    "ds-harness-remote": "^0.4.23"
  },
  "dsh": {
    "profile": {
      "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "ds-harness-remote", "@local/skills-panel"]
    }
  }
}
```

可以清楚看到三种来源：**随发行版内置**（`@deepseek-ai/dsh-*`）、**npm 包**（`ds-harness-remote`）、**本地目录 link**（`link:` 指向磁盘上的插件源码，正是本机开发中的 `skills-panel` 和 `traj-translate`）。

### 2.2 安装命令就是 pnpm 透传

DSH 自带文档（`@deepseek-ai/dsh` README，随包 README.zh.md）原文：

```
| `dsh plugin --profile <name> <pnpm args>` | 通过在 profile 目录中转发给 pnpm 来管理该 profile 的插件。 |
```

命令行为实测确认为**纯 pnpm 透传**——`dsh plugin --profile desktop --help` 原样打印出 pnpm 自己的帮助：

```
Version 11.7.0
Usage: pnpm [command] [flags]
...
      add  Installs a package and any packages that it depends on
```

也就是说，"安装插件"就是 `dsh plugin --profile desktop add <包名>`，**没有 DSH 自有的市场检索步骤**。

### 2.3 插件管理器页面（不是市场）

`@deepseek-ai/dsh-client-ui-plugin-manager` 的随包文档（README.zh.md）对页面的描述：

> 使用 Web 侧栏的**插件**入口管理 profile 已安装的组合包，以及安装随附、默认关闭的官方组合包。可以启停组合包及其行、在 Host 读出 spec 指向什么之后安装组合包、查看 pnpm 输出、停止一次运行，并启用它新增的包。卸载会要求确认。

页面只有两个分组：**官方**（安装随附、默认关闭的组合包，属于实验性的打"实验性"标签）与**已安装**（profile 持有的组合包）。

**"添加插件"接受的是**：包名（可带版本）、Git 地址、压缩包或本地绝对路径。

> 值得注意：页面里所谓"**安装源**"，指的是 **npm 注册表（registry）**，不是插件目录。选项为 pnpm 自身的注册表、Host 配置的镜像、手动输入的 http(s) 地址；官方源与镜像通过向 `https://registry.npmjs.org/-/ping` 和 `https://registry.npmmirror.com/-/ping` 发 HTTPS ping、取最先返回 2xx 者来选定（默认 1500 ms 超时，结果缓存 5 分钟）。

**它没有任何目录、分类、搜索、评分、推荐或榜单**——列表里只有你已经装了什么、以及官方随包但默认关闭的 bundle。

### 2.4 官方明确写下的限制（原文摘录）

来自 `@deepseek-ai/dsh-client-ui-plugin-manager` README「已知限制与延期工作」一节，这几条最直接回答了"为什么说它不是一个市场"：

> - **没有版本选择器**——spec 按 pnpm 接受的写法输入；页面不列出注册表版本，也不提供升级。拒绝提示和已安装插件的不兼容原因会告诉用户：profile 安装的插件通过卸载后重新安装来升级，随 DSH 提供的插件随 DSH 升级。
> - **每次读注册表都要运行 pnpm**——打开对话框、检查、安装各问一次 pnpm 自身配置指向哪里；没有 pnpm 的机器读作未知，不提供备选。
> - **只有组合包可管理**——没有 bundle patch 的依赖在安装前就被拒绝；加载普通插件模块仍是文件操作。
> - **安装源选择只属于本浏览器**——它存在 `localStorage` 里。

另外，安装对话框自己的提示文字也写明："插件安装后暂不支持自动更新：升级需先卸载再安装新版。"

**没有版本选择、没有注册表版本列表、没有自动更新、没有发现/搜索能力** —— 这几条恰恰是"市场"的必要功能，DSH 一个都没做。

### 2.5 官方插件确实发布在 npm 上

`@deepseek-ai/dsh` 的 npm registry 元数据（直接读 `https://registry.npmjs.org/@deepseek-ai%2Fdsh`）：

| 字段 | 值 |
|---|---|
| description | dsh CLI: profile launch, plugin management, and configuration inspection |
| dist-tags | `latest` = **0.2.0-rc.2**；`next` = 0.2.0-rc.2；`alpha` = 0.1.7-alpha.2 |
| repository | `git+https://github.com/deepseek-ai/deepseek-harness.git` |
| maintainers | imccyu, tianyicui-deepseek |
| created | 2026-08-10 |
| 已发布版本数 | 29 个（0.0.1-rc.1 → 0.2.0-rc.2） |

本机 `app.asar` 内 `"version": "0.2.0-rc.2"`，与 npm 上的 `latest` 一致。桌面端 `app-update.yml` 显示更新通道为 `channel: nightly`，发布者为杭州深度求索（`CN=Hangzhou DeepSeek Artificial Intelligence Co., Ltd.`）。

**注意**：整个版本号序列里几乎全是 `-rc` / `-alpha` 预发布号，`latest` 本身也是 `0.2.0-rc.2`。这说明 DSH 处于**预发布 / 早期阶段**——一个官方插件市场在这种阶段通常还没被提上日程。官方 README 也自己标注为 **"Developer preview"**，并加粗警告 **"THERE WILL BE COMPATIBILITY-BREAKING CHANGES."**

---

## 三、官方对"插件市场"的态度：有人提过，官方没接

这是本次调研最有价值的一条——它把"没有市场"从"我没找到"变成了"官方知道但没做"。

### 3.1 社区正式提案：把插件市场做成一个插件

GitHub Discussion **#1825**「把「插件市场」本身做成一个插件（Plugin Marketplace as a Plugin）」：
<https://github.com/deepseek-ai/deepseek-harness/discussions/1825>

| 字段 | 值 |
|---|---|
| 分类 | **Ideas**（官方为"分享新功能想法"设的分类） |
| 作者 | `szx-a`，`author_association = NONE`（**非官方成员**，纯社区用户） |
| 创建 | 2026-08-15 |
| 评论数 | 4（**全部来自社区用户 `Electricitysheep` 与作者本人，无一条官方回复**） |
| 点赞 | 1 |

提案正文自己陈述了现状（可与本报告第二节互相印证）：

> DeepSeek Harness 的「一切皆插件」在**技术层面**已经成立……但在**分发层面**，插件仍只能通过本地文件扫描被发现，没有下载、安装、卸载的用户路径。
>
> - 现有插件设置页 `ui-settings-plugin-inventory` 是**只读的 Loader 清单**，其 Known Limitations 明确写着缺 **provenance（出处）、grouping by source（按来源分组）、plugin mutation controls（安装/卸载）**。
> - 官方 `CONTRIBUTING.md` 明确鼓励社区插件（关联 `dsh-plugin` topic 分享）……
>
> 结论：分发与发现是当前生态链上**缺失的一环**。

提案的核心设计是"市场即元插件"——可启停、挂进 `settings.plugins.tab` slot 成为第三个 tab，并沿用 cordis 的 trust 哲学"**呈现差异而非强制执行**"。

**判断**：这说明"缺市场"不是我的观察偏差，而是**社区公认的生态缺口**，并且已经有人正式提出。但提案至今停在 Ideas 分类，**零官方回应**，全仓库 discussion 标题搜索 `marketplace` 命中 **0**。截至调研时点，官方没有任何要做市场的表态。

### 3.2 官方指定的发现渠道：GitHub topic（且已严重注水）

官方 README 让插件作者"给你的仓库打上 `dsh-plugin` topic 以便被发现"。实测这个渠道的规模与质量：

| 指标 | 实测值 |
|---|---|
| 打了 `dsh-plugin` topic 的仓库总数 | **17,239** |
| 其中名称/描述含 "dsh" 的 | **15,494** |
| 该 topic 下 star 最高的仓库 | `deepseek-ai/deepseek-harness` 本身（242,410） |

但**按 star 排序的结果明显被污染**：前几名里混进了 `reactive-resume/reactive-resume`（简历生成器）、`freestylefly/awesome-gpt-image-2`（图像提示词库）、`volcengine/OpenViking` 等与 DSH 无关的项目——它们只是把 `dsh-plugin` 当关键词蹭流量。

这带来一个务实的结论：**官方指定的发现机制是"打标签"，它没有审核、没有目录、没有排序治理，因此天然容易被注水**。这正是各类第三方"市场"插件试图解决的问题——它们做的事就是把 `dsh-plugin` topic 扫出来、按 star 排序、加一层 UI。

一个有意思的旁证：`dsh-plugin-marketplace` 这个包的自述就写着"在设置页直接浏览 `github.com/topics/dsh-plugin`，支持搜索、按 Star 排序"——**它扫的正是官方 README 指定的那个 topic**。

### 3.3 社区自发的"市场"替代品

除了插件形态的市场，社区还长出了这些发现层：

- **`topic:dsh-plugin` topic 本身**（官方指定，15k+ 仓库，无治理）
- **awesome 列表**：`awesome-dsh-plugin/awesome-dsh-plugin`（star 17,623）、`dshbase.com` 目录站
- **手册类**：`Electricitysheep/dsh-handbook`（其第 7 章专门讨论"插件市场标准化是必然方向"）
- **Discord 社区**（官方 README 提供邀请链接）

---

## 四、第三方"插件市场"生态（⚠️ 非官方）

正因为官方没有，社区自己补了一批市场插件。在 npm 上搜索实测结果：

| 包名 | 最新版 | 说明（包自述） | 维护者 |
|---|---|---|---|
| `dshmarket` | 1.66.8 | "DSH 可视化插件市场：逛一逛，点一下，装好。" 有独立站点 `dshmarket.com`，147 个版本 | fkysly |
| `dsh-plugin` | 1.4.13 | "社区插件市场…10000+ 人工精选社区插件" | — |
| `dsh-plugin-marketplace` | 0.4.1 | 浏览 `github.com/topics/dsh-plugin`，按 Star 排序 | scorp1o117 |
| `@springbrand/dsh-plugin-marketplace` | 1.0.8 | 面向 DSH profile 的可视化市场 | — |
| `@starpivot/dsh-plugin-marketplace` | 0.1.15 | "可安装的 DSH 插件市场，替换设置里的插件页" | — |
| `@dshindex/dsh-plugin-marketplace` | 0.1.0 | 用户确认式 DSH Index 发现 | — |
| `@w2112515/dsh-plugin-marketplace` | 0.2.4 | 树外可安装市场 bundle | — |
| `@lovstudio/dsh-plugin-marketplace` | 0.1.0 | local-first，GitHub + dshfind 双 provider | — |
| `@ruihuahe/dsh-plugin-marketplace` | 0.1.0 | 生成式目录 + npm 安装 | — |
| `hi-dsh` | 0.1.0 | "a dsh plugin marketplace" | — |

同一生态里还有一堆周边工具：`dsh-find-plugin`（在 agent 内搜 GitHub dsh-plugin topic 并按 star 排序）、`find-skills` 式的发现器、`create-dsh-plugin-cli`（脚手架）、`dsh-plugin-guide`（开发知识库）、`dsh-plugin-ops-bundle`（插件健康面板）、`dsh-plugin-observatory`（兼容性审计）等。

### ⚠️ 风险提示

1. **全部非 DeepSeek 官方出品**，维护者是个人账号（`fkysly`、`scorp1o117`、`liguobao` 等），与 `@deepseek-ai` 组织无关。官方文档里的"官方"分组**只指随 DSH 发行版附带、默认关闭的 bundle**，不指这些社区市场。
2. **命名高度同质化，存在抢注/仿冒空间**。同一个 `dsh-plugin-marketplace` 名字下同时存在 `@springbrand/`、`@starpivot/`、`@dshindex/`、`@w2112515/`、`@lovstudio/`、`@ruihuahe/` 六个不同 scope 的包，普通用户极难分辨谁是"正版"。
3. **市场类插件权限等同于任意代码执行**。DSH 插件是直接挂进 Cordis 运行时树的 npm 包，能读写你的 profile、配置文件、会话数据，并继承 agent shell 的环境与凭据。DSH 官方文档也提示：安装成功**不代表模块一定能激活**，且检查不受信任插件前应先阅读 schema dump 的安全说明。
4. **供应链风险已被 DSH 自己承认并缓解**。本机 pnpm 日志里能看到 `Lockfile passes supply-chain policies`，以及 pnpm 会**拦截依赖的安装脚本**并要求显式授权（"允许这些脚本并重试"，授权写入 profile 的 `pnpm-workspace.yaml`）。这是防护，但也说明插件装的确实是可执行代码。
5. **本机已装 `ds-harness-remote`（v0.4.23 → 0.4.27）**，这是第三方包（维护者 `liguobao`，自述为"端到端加密的远程访问"），与市场无关，但同属第三方插件，值得知悉。

---

## 五、置信度与未解问题

### 直接验证（高置信度）

- `app.asar` 全文字符串检索：`插件市场` = 0、`市场` = 0、`插件管理` = 27、`marketplace` = 14（**全部为第三方依赖文档**）。这是"官方无市场"最硬的本地证据——如果存在市场功能，不可能连词条都没有。
- `dsh --help` 与 `dsh plugin --profile desktop --help` 实测输出：后者是 pnpm 11.7.0 的原样帮助，确认插件操作 = pnpm 透传。
- 本机 profile 的 `package.json`、`.plugin-manager/logs/*/pnpm.log` 实测：插件确为 profile 目录下的 pnpm 依赖，日志含 supply-chain policy 检查与构建脚本拦截。
- `@deepseek-ai/dsh` 的 npm registry 元数据实测（含仓库地址、维护者、完整版本列表）。
- 本机 asar 内版本号 `0.2.0-rc.2` 与 npm `latest` 一致。
- **官方 README（raw.githubusercontent.com，master 分支）实测抓取**：`dsh-plugin` topic 是官方指定的发现渠道。
- **官方 CONTRIBUTING.md 实测抓取**："not a mandate from us" + 目前不接受外部 PR。
- **GitHub API 实测**：Discussion #1825 元数据与全部 4 条评论（作者 `szx-a`，`author_association=NONE`，无官方回复）；discussion 标题搜 `marketplace` 命中 0；`topic:dsh-plugin` 仓库数 17,239。

### 引自 DSH 自带文档（权威，但未逐行对照源码）

- 插件管理器页面的行为、分组、"安装源 = 注册表"、registry ping 探测逻辑、四条"已知限制"原文。这些来自随 asar 打包的 `packages/boot/plugin-manager/README.zh.md` 与 `packages/client/ui-plugin-manager/README.zh.md`。文档与实现理论上可能有时差，但作为厂商自己的功能声明足够可信。

### 未能验证 / 存疑

- **官方文档站点深层页面未取到**：`https://deepseek-harness.github.io/deepseek-harness/` 首页 200 但内容为空壳（JS 渲染），`/docs/user/guide/index.md` 返回 404。因此**没有逐页通读官方文档**来确认是否存在任何"市场"相关页面。不过 README 与 CONTRIBUTING.md 这两个最权威的入口已经给出明确口径，结论不受影响。
- **官方是否在 Discussions 里口头承诺过市场**：GitHub Discussions 支持用 GraphQL 检索正文，本次只用 REST 检索了**标题**（`marketplace` 命中 0）。正文中可能仍有提及，未穷尽。**注意 Discussion #1825 是社区提案而非官方承诺**，不要误读为官方路线图。
- **`dsh-plugin-marketplace` 在 npm 页面上带 ⚠️ 标记**（搜索结果里的 `?activeTab=dependents#1` 前缀显示为 "⚠️"）。npm 包页返回 403（Cloudflare 拦截），未能确认该警告的具体性质（安全公告？弃用？），建议安装前自行查看该包页面。
- 社区包自述的"10000+ 插件"等数字**未经验证**，很可能是营销话术。
- 第三方目录站 `dshbase.com`、`dshmarket.com` 为社区站点，未核实其运营方与数据来源。
- `topic:dsh-plugin` 的 17,239 这个数字**包含大量蹭关键词的无关仓库**（按 star 排序前列就混入简历生成器等），因此**不能当作"DSH 插件真实数量"**。

### 矛盾的来源

- 中文媒体报道（凤凰网转载）称 DSH v0.2 预览版"**新增插件管理**"——与本次调研一致，**说的是插件管理，不是插件市场**。若把它读成"上线了市场"会是误读；从证据看，那条新闻的描述反而是准确的。

### 一个容易误读的点

本报告第二节引用的官方插件管理器文档里，页面确实有一个叫「**官方**」的分组。**它不是"官方认证的插件市场"**，而是"随 DSH 发行版附带、默认关闭、点一下才能启用的 bundle"。同理，插件管理器页面里的「**安装源**」指的是 npm registry，不是插件来源目录。这两处最容易被读成"官方市场"，需要特别区分。

---

## 六、一句话总结

**DSH 官方没有插件市场，只有一套基于 pnpm + Cordis 的插件管理体系**：插件是装进 profile 的 npm 包（或本地 `link:` 目录），`dsh plugin` 命令透传 pnpm，Web 侧栏的"插件"页面负责启停与安装。它**不列出注册表版本、不提供升级、不提供检索发现**，官方文档自己把这些列为已知限制；官方指定的"发现"手段是**给 GitHub 仓库打 `dsh-plugin` topic**（15,000+ 仓库且被关键词注水）。社区已经正式提案把市场做成一个插件（Discussion #1825），但**零官方回应**，官方 README 也把项目标为 "Developer preview" 并声明仓库"not a mandate"。你现在看到的"DeepSeek Harness 插件市场"，一律是第三方社区包（`dshmarket`、`dsh-plugin`、各 scope 的 `dsh-plugin-marketplace` 等）后挂上去的，与 DeepSeek 无关，且因插件拥有完整代码执行权限而需要谨慎对待。
