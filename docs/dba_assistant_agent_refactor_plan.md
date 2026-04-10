# DBA Assistant AI Agent 化改造方案

## 1. 文档目的

本文用于明确当前 `dba_assistant` 项目的改造方向，目标不是继续把项目包装成 “看起来像 AI Agent 的 Python 黑盒”，而是将其收敛为一个真正的 **AI Agent 工具**：

- **LLM 负责理解、规划、选择能力链路与作出决策**
- **Agent Runtime 负责执行、约束、审计、审批、记忆与工具编排**
- **Python 仅承担轻量的运行时职责，不承接重业务决策，不演化成新的黑盒 orchestrator**

---

## 2. 目标架构原则

### 2.1 总原则

这个项目必须符合以下原则：

1. **LLM 是大脑，Agent 是四肢**
   - 决策、步骤选择、工具选择、是否需要调用某个能力，应尽量由 LLM 基于 system prompt、skills、memory、tool descriptions 来完成
   - Python 不能抢夺业务决策权

2. **Python 必须保持轻量**
   - Python 可以做运行时边界控制
   - 但不能变成一个“先判断路径、再决定走哪套流程”的重型业务调度器

3. **必须使用 deepagents 的标准能力**
   - HITL
   - Memory
   - Tools
   - Skills
   - system prompt
   - 统一 Agent Runtime

4. **一个生产项目只能有一套主 Agent 叙事**
   - 不能同时保留多个职责重叠、prompt 不一致、入口不一致的 Agent Builder
   - 不能让旧时代的 phase 概念继续污染生产代码命名

---

## 3. 当前问题判断

当前项目的核心问题，不是“完全没有 Agent”，而是：

> **表面上接入了 Deep Agents SDK，但关键执行链路仍然被 Python 快捷逻辑提前分流，导致 LLM 没有真正成为决策中心。**

这会导致以下问题：

### 3.1 双 Agent / 双入口并存

当前仓库中存在至少两套 Agent 叙事：

1. `agent_factory.py` 中的 `build_phase2_agent`
2. `orchestrator/agent.py` 中的统一 Agent

这会带来以下风险：

- prompt 不一致
- tools 装配方式不一致
- 能力边界不一致
- 开发者不知道哪套才是生产标准
- 后续维护时不断出现“旧逻辑复活”

### 3.2 Python 快捷路径绕过 Agent

当前存在某些本地 RDB 场景下，Python 先判断、先执行、直接返回的行为。

这会导致：

- LLM 没有真正参与规划
- skills 没有真正生效
- system prompt 没有真正成为执行依据
- tool calling trace 无法体现“模型做了什么决策”

### 3.3 工具粒度过大，仍然是黑盒按钮

当前一些工具仍然属于“大而全工具”：

- 对模型来说只是“分析一下”
- 但工具内部又可能继续做路径判断
- 模型看不到里面的执行分叉
- 结果仍然是 Python 内部决定业务路径

### 3.4 `skills` 概念混用

当前项目中，“skills” 同时用于：

1. 给模型看的 Markdown 技能说明
2. Python 代码层的能力模块

这会造成语义冲突：

- 哪些是模型技能
- 哪些是代码能力
- 哪些该写在 `SKILL.md`
- 哪些该作为 tool / adaptor / capability 实现

### 3.5 命名不规范

当前代码中仍带有大量历史性命名，例如：

- `build_phase2_agent`
- `run_phase2`
- `phaseX`
- `path_abc`
- `path_mode`

这些命名会带来两个问题：

1. 业务语义不清晰
2. 把历史阶段性实现误当成长期架构

---

## 4. 必须明确的一条边界：不是所有 Python 逻辑都该移交给 LLM

我同意：**不是所有 Python 逻辑都要移交给 LLM。**

但同时必须再加一条更重要的约束：

> **Python 可以存在，但必须是轻量的 Agent Runtime 逻辑，而不能成为重型业务决策器。**

---

## 5. 哪些逻辑应该保留在 Python 中

这些逻辑可以保留，而且本质上属于 **Agent Runtime 逻辑**，不是业务决策逻辑。

### 5.1 输入归一化

例如：

- 将 CLI 输入整理成统一 request object
- 识别显式给出的本地文件路径
- 识别显式给出的远程 Redis / SSH / MySQL 参数
- 将用户输入整理成模型可消费的上下文

这里的职责是：

- **做输入标准化**
- **不做业务路线选择**

### 5.2 Tool 注册与调用包装

例如：

- 把 Python 能力暴露成标准 tool
- 统一 tool schema
- 参数校验
- 错误包装
- 执行结果标准化返回

这里的职责是：

- **让能力可被 Agent 调用**
- **而不是替 Agent 做决定**

### 5.3 HITL 强制执行

例如：

- 某些高风险操作必须 approval
- fetch remote file
- 写入 MySQL
- 对生产环境执行破坏性操作

这里必须由 Runtime 强制，而不能只靠模型“口头征求同意”。

### 5.4 安全与凭据注入

例如：

- SSH 凭据读取
- MySQL 凭据读取
- secrets 注入
- 环境变量管理

这些都应由 Python runtime 负责，不应该由模型自由推断或拼接。

### 5.5 审计与日志

例如：

- 记录本次调用了哪些工具
- 记录 approval 事件
- 记录关键输入输出摘要
- 记录报表生成动作

### 5.6 Memory 接入与持久化包装

例如：

- 将会话事实、用户偏好、允许长期保留的信息，转为 runtime 可用的 memory source
- 持久化 memory note
- 在后续会话恢复时注入上下文

---

## 6. 哪些逻辑不能继续放在 Python 中

以下逻辑不能继续由 Python 主导，否则项目就会继续退化为“Python orchestrator + LLM 外壳”：

### 6.1 业务路径选择

例如：

- 看到是本地 RDB，就直接跳过 Agent 执行
- 看到文件大，就自动切换到另一条分析路径
- 看到参数里有 MySQL，就默认走 MySQL 分析

这些都不应该由 Python 先拍板。

### 6.2 自动选择策略

例如：

- direct 模式
- parse 模式
- mysql stage 模式
- remote fetch 模式

这些应尽量由 LLM 在 skill 指引下决定。

### 6.3 大而全的黑盒工具内部再决策

例如：

- 一个工具对外叫“analyze”
- 但内部又自己判断要不要写 MySQL、要不要 SSH、要不要换模式

这会让模型失去真实决策能力。

---

## 7. 这里有一个额外的重要约束：Python 不能变重

这是本次改造的硬约束。

### 7.1 不允许出现的坏方向

不允许将系统改造成：

- 一个超重的 Python orchestrator
- 一个只有“最后润色和说明”的 LLM
- 一个由 Python 预先写死业务分支的伪 Agent 框架

### 7.2 Python 应保持在什么程度

Python 层应保持：

- 薄入口
- 薄 Runtime
- 标准 Tool 包装
- 审批守卫
- 安全边界
- 审计能力
- Memory 接口层

而不应承担：

- 复杂 if/else 路由树
- 业务意图判断树
- 自动切换分析模式
- 过重的流程编排

---

## 8. 关于 MySQL 分析路径的强约束

这一条必须单独明确：

> **不能因为 RDB 过大，就自动切换到“写入 MySQL 再分析”。**

这不是一个可接受的默认业务逻辑。

### 8.1 MySQL 路径的正确定位

写入 MySQL 再分析，应该只是一个 **可选能力**，而不是默认策略。

它只能在以下情况下触发：

1. **用户在 prompt 中明确指定**
   - 例如：
     - “请导入到 MySQL 后分析”
     - “先写到 MySQL，再做分析”
     - “通过 MySQL staging 的方式分析”
     - “结果请基于 MySQL 中间表做分析”

2. **用户已明确确认**
   - 如果未来你允许二次确认型流程，那么也必须是在清楚告知后，由用户明确批准

### 8.2 不允许的行为

以下行为都不允许：

- 因为文件大，自动走 MySQL
- 因为 direct 模式慢，自动走 MySQL
- 因为 Python 判断“更高效”，自动走 MySQL
- 因为模型自己觉得方便，就直接写 MySQL

### 8.3 设计要求

因此，MySQL 相关 tool 的设计应满足：

1. Tool 本身是独立能力，不是 analyze 的隐藏子过程
2. Tool description 明确写明：
   - 这是一个高成本/有副作用路径
   - 仅在用户明确要求或明确批准时使用
3. system prompt / skill 中必须明确禁止“自动切换到 MySQL”
4. HITL 需要兜底保护
5. 审计日志必须记录是谁触发、何时触发、依据是什么

---

## 9. 对“这些 Python 必要逻辑，是不是 Agent 的逻辑？”的判断

我的判断是：

> **这些 Python 必要逻辑，属于 Agent Runtime 逻辑，但不属于 Agent 的大脑逻辑。**

更准确地说，应该拆成两层：

### 9.1 Agent Brain（模型脑）

由 LLM 负责：

- 理解用户意图
- 阅读 system prompt / skills / memory
- 决定调用哪些工具
- 组织执行步骤
- 决定如何解释输出
- 决定何时需要进一步信息

### 9.2 Agent Runtime（执行体）

由 Python 负责：

- 暴露工具
- 校验参数
- 审批拦截
- 安全控制
- 结果封装
- 审计记录
- Memory 接入
- 上下文注入

所以：

- **这些 Python 逻辑是 Agent 的运行时逻辑**
- **不是 Agent 的业务决策逻辑**
- **不能用“这是 Agent 逻辑”来合理化一个超重的 Python orchestrator**

---

## 10. 改造总体方向

本次改造建议遵循以下方向：

### 10.1 收口为单一生产 Agent

生产代码中只保留一个统一的 Agent Builder 和一个统一运行入口。

建议目标：

- 只有一个主 `build_agent_runtime(...)`
- 只有一个主 `run_agent_request(...)`

旧的 phase 风格入口全部移出生产路径。

### 10.2 移除 Python 快捷执行分流

显式本地 RDB 也应先进入 Agent Runtime。

可以允许 Python 做：

- 路径识别
- 输入归一化
- 明确告诉模型“这是用户显式提供的文件”

但不能允许 Python 直接执行分析并绕过 Agent。

### 10.3 工具重切粒度

工具应改成 “模型可决策、但不会陷入实现细节” 的粒度。

更合适的方向是：

- `inspect_local_rdb`
- `parse_local_rdb`
- `analyze_parsed_dataset`
- `discover_remote_rdb`
- `fetch_remote_rdb_via_ssh`
- `stage_dataset_to_mysql`
- `load_dataset_from_mysql`
- `render_report`

原则是：

- 不要一个工具把所有事都做完
- 不要让一个工具内部偷偷做二次业务决策

### 10.4 重写 Skill 文档

`SKILL.md` 必须从“功能简介”改造成“给模型看的操作手册”。

应包含：

- 什么时候直接分析
- 什么时候先 inspect / parse
- 什么情况下可以 remote fetch
- 什么情况下必须 approval
- 什么情况下可以生成 docx
- **什么情况下才允许走 MySQL**
- **明确写出：未获 prompt 明确要求，不得切换到 MySQL staging**

### 10.5 system prompt 只保留长期规则

system prompt 应主要承载：

- 身份
- 运行边界
- 审批规则
- 安全规则
- 不得伪造、不得绕过显式输入
- 不得自动切换到 MySQL

业务流程细节尽量下沉到：

- SKILL.md
- tool descriptions
- memory context

### 10.6 Memory 从“静态文档注入”升级为运行时记忆

Memory 不应只有仓库级 `AGENTS.md`。

后续建议接入：

- 用户偏好
- 默认输出偏好
- 常用分析 profile
- 允许保留的工作上下文
- 会话总结性 note

---

## 11. 命名规范整改要求

生产代码中不应再出现：

- `phase1`
- `phase2`
- `phase3`
- `path_xxx`
- `abc_path`
- `run_phaseX`
- `build_phaseX_agent`

### 11.1 命名改造方向

应改为业务语义命名，例如：

- `build_phase2_agent` → 删除或迁移为 debug/example
- `run_phase2` → `run_debug_agent` 或直接删除
- `_run_phase3_analysis` → `_run_analysis_service`
- `path_mode` → `execution_strategy`
- `direct_rdb_analysis` → `direct_file_strategy`
- `database_backed_analysis` → `mysql_staged_strategy`
- `preparsed_dataset_analysis` → `parsed_dataset_strategy`

### 11.2 命名原则

命名必须体现：

- 业务能力
- 运行职责
- 长期稳定语义

不能继续保留阶段性实现遗产。

---

## 12. 建议保留与建议清理的部分

## 12.1 建议保留

可以保留并继续演进的部分：

- 统一 CLI 薄入口
- HITL / approval 机制
- adaptor 层
- 统一 Agent Runtime 主入口
- `/skills` 目录中的模型技能文档
- `AGENTS.md`
- 与 tools / capabilities / adaptors 相关的实现层

## 12.2 建议清理或迁移

建议清理、迁移或降级为 legacy/debug 的部分：

- 旧的 `build_phase2_agent`
- 旧的 `run_phase2_request`
- 旧的 `run_phase2`
- 与旧入口耦合的 tool registry
- 所有绕过 Agent 的本地快捷分析逻辑
- Python 包中名为 `skills` 但本质是实现代码的目录命名

---

## 13. 建议的改造顺序

为降低风险，建议按以下顺序推进：

### 第一步：锁定外部行为
- 为现有 CLI 和关键输入场景补测试
- 保证改造过程中外部接口不乱

### 第二步：统一生产入口
- 只保留一个主 Agent Builder
- 只保留一个主运行入口

### 第三步：移除绕过 Agent 的快捷分流
- 显式本地 RDB 也必须进入 Agent Runtime

### 第四步：重切 tool 粒度
- 把“黑盒总代办工具”拆成模型可选择的业务级工具

### 第五步：重写 system prompt / skills / tool descriptions
- 明确 LLM 决策边界
- 明确 MySQL 使用前提
- 明确审批规则

### 第六步：接入更真实的 Memory
- 从仓库文档注入，升级为运行时可用的 session/project memory

### 第七步：删除 legacy 命名与旧文件
- 清理 `phase/path` 相关遗留代码
- 完成命名收口

---

## 14. 本次改造的验收标准

改造完成后，应至少满足以下标准：

### 14.1 统一 Agent 入口
任意正式请求都只能通过同一套 Agent Runtime 进入执行链。

### 14.2 LLM 真正负责决策
在 trace 中可以看出：

- 模型读到了 skill
- 模型决定了调用哪些工具
- 模型决定了下一步执行顺序

### 14.3 Python 保持轻量
Python 不承担重业务路由，不存在大规模 if/else 路径树。

### 14.4 HITL 是强制机制
高风险操作必须由 Runtime 守卫，而不是仅靠模型“提醒用户”。

### 14.5 MySQL 不再被自动启用
除非 prompt 显式指定或明确确认，否则不得执行 MySQL staging / import / 分析链路。

### 14.6 Memory 不再只是静态文档
至少具备最小可用的运行时记忆能力。

### 14.7 命名完成收口
生产代码中不再出现 `phase x / path abc` 风格命名。

---

## 15. 最终结论

我的结论是：

### 15.1 需要先清理旧代码
但不是推倒重来，而是要进行一次有边界的收口：

- 收口运行时入口
- 收口命名
- 收口决策边界
- 移除绕过 Agent 的快捷链路

### 15.2 需要从“Python 主导流程”改为“LLM 主导决策”
项目的目标应明确为：

- **LLM 负责决策**
- **Agent Runtime 负责执行与守卫**
- **Python 保持轻量，不变成新的黑盒 orchestrator**

### 15.3 MySQL 路径必须降级为显式能力，而不是默认策略
尤其需要明确：

> **不能因为 RDB 大，就自动切到 MySQL。**
>
> **只有 prompt 明确指定或明确确认后，才允许执行 MySQL staging / import / 分析。**

---

## 16. 一句话版本

这个项目接下来的正确方向不是“继续优化 Python orchestration”，而是：

> **把它改造成一个真正由 LLM 决策、由 Deep Agents Runtime 执行、由 HITL/Memory/Tools/Skills/system prompt 共同驱动的轻量型 AI Agent。**
