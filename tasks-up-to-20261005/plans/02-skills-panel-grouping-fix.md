# 实施计划：skills-panel 严格树形分段与全量展开重构

## 目标描述

根据用户明确决策，对 `@local/skills-panel`（`skills-panel/client.js`）的前端渲染层进行彻底重构：
1. **分类第一层**：区分「用户安装（~/.agents/skills 等）」、「系统内置」与「工作区」（如有）。
2. **纯粹递归树（TreeView）**：内部根据技能名称中的 `-` 横杠（`a-b-c-d`）逐段构建树形结构：
   - 保留所有前缀（如 `sh-` 作为 `sh` 分支，内部再分 `agy`、`zed` 等）；
   - 只要当前段有 >= 2 个技能共享，即成目录分支（Branch）；否则作为本级叶子技能（Leaf）；
   - 每个节点使用绝对唯一的路径作为 ID（如 `user/lark`、`user/lark/workflow`、`user/sh`、`user/sh/zed/lsp`）。
3. **交互规范（用户拍板）**：
   - **默认全部展开**：首次进入时，所有大类和树枝目录默认全部处于展开态，直观一览无余；
   - **独立折叠/展开**：各节点独立维护收起状态（`collapsedSet: Set<string>`），点击任意分支仅切换自身折叠/展开，绝不关闭兄弟分支，绝不破坏父子层级；
   - **支持搜索与快捷折叠**：搜索时强制展开所有命中链路，清空时还原用户状态；
   - **持久化**：用户手动折叠的节点路径存入 `localStorage`。

---

## 变更方案

### 组件：`skills-panel/client.js`

#### [MODIFY] `skills-panel/client.js`

1. **废弃旧前缀剥离与消歧别名机制**
   - 彻底删除 `AUTHOR_PREFIX` 特殊提升逻辑；
   - 删除复杂脆弱的 `disambiguate`、`qualifiedLabel`；
   - 标签直接为当前段的原名（首字母大写或原词展示）。

2. **精简高效的递归树构建函数 `buildSegmentTree`**
   - 输入：当前层的一组技能，当前前缀路径 `prefixParts`；
   - 逻辑：
     - 将所有技能按下一段名称进行分组；
     - 若某组技能数量 >= 2，生成子分支节点 `Branch`，递归调用 `buildSegmentTree`；
     - 其余单项直接作为本层的 `Leaf` 技能行；
   - 节点的唯一 `id` 为路径拼接，例如 `user/sh/zed/lsp`，绝对唯一且具备天然层级父子关系。

3. **独立折叠状态模型（Set-based）**
   - 存储 `collapsed: Set<string>`（用户显式收起的节点 ID）；
   - 展开判定：`isExpanded(id) = searching || !collapsed.has(id)`；
   - 切换操作：`toggle(id)`：若在 `collapsed` 中则删除（展开），若不在则加入（收起），写入 `localStorage`；
   - 由于默认全部展开，空 Set 即代表全展状态，无需预先计算庞大的 open 列表，初始加载瞬间完成且无任何状态死锁。

4. **递归树视图渲染 `renderNode` 与缩进样式**
   - 来源 L1（用户安装、系统内置）：使用独立的大类标题头；
   - L2 及更深子分支：根据 `level` 动态计算缩进（如 `padding-left: ${10 + (level - 1) * 14}px`）；
   - 叶子技能行：同样附带对应层级的缩进，保持树形对齐美观。

---

## 验证方案

### 自动化测试
1. 运行 `test-grouping.mjs` 与更新后的 `test-render.mjs`：
   - 验证树形结构不漏项、不重项（110 项全覆盖）；
   - 验证 `sh-` 自然成为 `sh` 分支，其下包含 `agy`、`zed`、`lark` 等子分支；
   - 验证初始状态下所有分支 `aria-expanded === "true"`；
   - 验证点击 `Workflow` 仅收起/展开 `Workflow`，父级 Lark 及其余分支保持不变。
2. 运行真实技能目录预览：
   ```powershell
   $env:DSH_TEST_SKILLS_ROOT='C:\Users\29580\.agents\skills'; node skills-panel/design/preview-tree.mjs
   ```

### 人工验证
- 刷新 DeepSeek Harness 桌面端页面；
- 检查技能面板：
  1. 刚进入时所有分类全部展开；
  2. 点击 `Lark` 能够正常收起 Lark，其他分类（如 `sh`、`redis` 等）不受任何影响；
  3. 点击 `Workflow`，仅切换 Workflow 自身的收起与展开；
  4. 点击 `系统内置`，可单独折叠/展开系统内置模块；
  5. 搜索功能正常工作。
