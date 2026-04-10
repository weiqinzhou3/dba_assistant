# DBA Assistant: 从黑盒脚本到 AI Agent 的进化报告 (v2)

## 1. 核心定位：Harness Engineering (挂载工程)

本项目已完成从“Python 主导流程”向“LLM 主导决策”的架构转型。

### 1.1 大脑与四肢的解耦
- **大脑 (LLM)**: 负责理解用户意图、查阅 `SKILL.md` 手册、规划执行步骤、决定工具调用顺序。
- **四肢 (Python Runtime)**: 负责暴露原子工具、注入凭据、强制执行 HITL (人工审批)、安全审计及结果归一化。
- **挂载点 (Harness)**: 通过 `orchestrator/tools.py` 将复杂的 DBA 能力平整地挂载到 Agent 运行时中。

---

## 2. 架构演进：废除黑盒，确立 SOP

### 2.1 移除“作弊路径” (Kill the Shortcut)
- **重构前**: Python 看到本地 RDB 路径就直接内部调用分析逻辑，绕过了 LLM。
- **重构后**: 删除了 `_run_explicit_local_rdb_analysis`。任何请求（包括本地文件）都必须通过 `agent.invoke()`。
- **意义**: 确保 `system_prompt` 和 `SKILL.md` 里的规则对所有操作生效。

### 2.2 工具原子化 (Atomized Tooling)
我们将大而全的“黑盒工具”拆解为 LLM 可自由组合的“原子积木”：

| 旧工具 (Blackbox) | 新原子工具 (Atomic) | 职责描述 |
| :--- | :--- | :--- |
| `analyze_local_rdb` | `inspect_local_rdb` | **先看眼**: 返回文件大小、元数据，供 LLM 决策。 |
| (隐藏逻辑) | `analyze_local_rdb_stream` | **流式算**: 仅用于小文件 (<512MB) 的内存流分析。 |
| (隐藏逻辑) | `analyze_staged_rdb` | **查 MySQL**: 仅用于分析已倒入 MySQL 的暂存数据。 |
| (自动触发) | `stage_rdb_rows_to_mysql` | **入库**: 显式调用，受 HITL 守卫，须 LLM 发起。 |

---

## 3. 标准作业程序 (SOP): Inspect -> Choose -> Act

我们在 `SKILL.md` 中为 Agent 注入了行业领先的 DBA 操作逻辑：

1.  **Inspect First (先探测)**: 严禁盲目分析。Agent 必须先调用 `inspect_local_rdb`。
2.  **Strategy Selection (选策略)**:
    - **小文件**: 直接调用 `analyze_local_rdb_stream`。
    - **大文件**: **严禁自动切换 MySQL**。Agent 必须告知用户文件很大，并建议（需用户确认）使用 MySQL 路径。
3.  **Execution (执行)**: 根据决策结果调用相应工具，并总结结论。

---

## 4. 运行守卫与安全 (Harness Guardrails)

- **HITL (Human-In-The-Loop)**: 对于 `fetch_remote_rdb_via_ssh` 和 `stage_rdb_rows_to_mysql` 等写操作/敏感操作，Agent 只能发起请求，审批权限牢牢掌握在人类手中。
- **审计溯源**: 每一条 LLM 的决策路径都记录在 `outputs/logs/audit.jsonl` 中，可回溯“大脑”为何做出特定选择。
- **规则约束**: 通过 `SYSTEM_PROMPT` 确立了“禁止伪造路径”、“禁止静默切换模式”等铁律。

---

## 5. 遗留清理 (Legacy Cleanup)

- **废除 Phase 概念**: 生产代码中不再出现 `phase2`, `phase3` 等阶段性命名。
- **入口归一化**: 统合为唯一的 `build_unified_agent`。
- **代码整洁**: 移除了冗余的 Agent Builder 和调试脚本，确保项目语义与 Master Plan 高度契合。

---

## 6. 结论

`dba_assistant` 现在的身份是一个**具备专业 DBA 知识的操作手册 + 强力的 Python 执行引擎**。

它不再是一个自动运行的脚本，而是一个：
- **听指挥**: 尊重用户明确要求的路径。
- **懂规矩**: 遵守大小限制和审批流程。
- **能思考**: 会根据文件现状动态调整分析方案。

**本项目已完成真正的 AI Agent 化改造。**
