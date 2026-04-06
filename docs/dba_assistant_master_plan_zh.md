# DBA Assistant 主计划

## 规则

- Deep Agent SDK 是运行时基础。
- AGENTS.md 是全局策略与安全边界层。
- Skill 是单个 DBA 场景的基本单位。
- Tool 是面向 Agent 的业务动作。
- Adaptor 是外部系统集成边界。
- 抽象按需引入。
- 在被真实复杂度证明之前，不引入自定义运行时框架。
- 危险写操作后续必须接入人工确认机制。

## 分阶段计划

### Phase 1：架构基础

- 状态：规划中
- 建立仓库结构与 Deep Agent 运行时装配
- 明确 Skill、Tool、Adaptor 与按需抽象入口的边界
- 增加 AGENTS.md、入口文件与基础测试

### Phase 2：运行时与模型配置

- 状态：规划中
- 通过 SDK 直接注册 skills 和 tools
- 先落地一个可用的 LLM 配置
- 保持运行时轻量，不自建大框架

### Phase 3：技能一 —— Redis RDB 分析报告

- 状态：规划中
- 定义明确的输入输出契约
- 实现 `analyze_redis_rdb`
- 增加文件输入 adaptor，并按需加入 parser
- 实现报告输出与基础测试

### Phase 4：技能二 —— Redis 巡检报告

- 状态：规划中
- 编写 `skills/redis-inspection-report/SKILL.md`，定义巡检范围、输入契约和输出契约
- 定义巡检覆盖范围与报告契约
- 实现 `collect_redis_inspection` 与 `generate_redis_inspection_report`
- 实现 Redis 巡检数据采集，覆盖基础信息、配置、持久化、复制、内存、慢日志、安全与风险项
- 支持在线采集与离线 inspection bundle 两种输入路径
- 实现生成 Word 报告，包含封面、执行摘要、巡检项明细、风险分级、整改建议和证据附录
- 新增端到端测试：给定 fixture，生成完整巡检 Word 报告

### Phase 5：审计与安全基线

- 状态：规划中
- 增加轻量级 JSONL 执行日志
- 记录 skill、输入摘要、工具调用、输出路径和执行结果
- 记录后续基于 interrupt 的人工确认策略

### Phase 6：技能三 —— Redis CVE 报告

- 状态：规划中
- 编写 `skills/redis-cve-report/SKILL.md`，支持自然语言时间范围解析、可选版本范围和数据源优先级
- 定义数据源覆盖范围与报告契约
- 实现 `collect_cve_intelligence` 与 `generate_redis_cve_report`
- 实现通过 NIST NVD CVE API 按时间范围抓取 Redis 相关 CVE，支持指数退避重试
- 实现从 MITRE/CVE 查询 Redis 相关数据
- 实现抓取 Redis 官方安全公告
- 实现查询 GitHub Security Advisories API（`redis/redis` 仓库）
- 实现合并去重，以 CVE ID 为主键，CVSS 评分以 NVD 为权威来源，按 CVSS 降序排列
- 实现当提供版本范围时，调用 LLM 逐条判定影响状态：受影响 / 不受影响 / 待确认
- 实现当未提供版本范围时，所有条目统一标注“需结合实际版本人工判断”
- 实现生成 Word 报告，包含封面、执行摘要、CVE 明细表、数据来源说明（含获取时间戳）和免责声明
- 单个抓取器失败不得阻塞整体流程；合并步骤记录哪些数据源不可用；报告中包含数据源可用性说明
- 新增端到端测试：给定模拟抓取器响应作为 fixture，生成完整 Word 报告

### Phase 7：后续扩展

- 状态：暂缓
- 接入审批的危险写操作
- 在 Redis 范围稳定后再扩展更多 DBA 技能

## 执行顺序

1. 完成阶段设计
2. 完成阶段代码实现
3. 运行单元测试、端到端测试与 smoke 检查
4. 更新阶段文档，并写清输出结果与下一阶段准入条件
