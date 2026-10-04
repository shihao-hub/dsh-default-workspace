# Agent Context Pointer

> **CRITICAL**: This repository is a sub-workspace (`tasks-v1`) of the parent project.
> All base conventions, Git commit rules, and environment guidelines are inherited from:
> `file://../AGENTS.md`

**ACTION REQUIRED**: Before executing any code changes or git commands, you MUST read and follow the root conventions in `../AGENTS.md`.

---

## 本任务工作区须知 (Workspace Guidelines)

1. **边界闭环**：
   - 当前工作区对应当前阶段的主力任务集合；
   - 本工作区产生的所有业务代码、脚本、临时文件及测试数据，**必须严格内聚在本目录树内**，严禁向父级根目录抛洒任何散落文件。
2. **规则继承**：
   - 严格遵守父级 `../AGENTS.md` 中的零污染原则、音视频等大文件不入库规范，以及规范化 Git 提交约定。
