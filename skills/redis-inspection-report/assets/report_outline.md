# Redis Inspection Report Outline

1. 巡检概述
2. 巡检范围与输入说明
3. 问题概览与整改优先级
4. 集群识别与架构总览
5. 巡检目标及方法
6. 系统配置检查
7. 操作系统检查
8. Redis 数据库检查
9. 风险与整改建议
10. 附录

第三章是领导视角执行摘要，只负责问题总览和优先处置方向，不展开大段证据。
固定包含 3.1 优先级速览、3.2 涉及节点与优先处置方向。3.1 默认全量展示
所有高风险/中风险集群；只有 section_contracts.yaml 明确 top_n 时标题才允许写 TOP N。
3.1 下直接展示优先级表格，不再渲染重复的 3.1.1 表格标题。
3.2 按问题类型分组，每个 3.2.x 问题类型使用两列信息表，不按集群堆砌段落。

第九章是运维落地视角，按 9.x 集群名、9.x.y 风险名称展开明细。
同一集群下同名风险必须合并为一个风险条目；字段顺序、加粗标签、
Review 展示条件和整改建议逐条换行规则以 section_contracts.yaml 为准，
每个 9.x.y 风险条目使用两列信息表，不使用单张宽表或自由段落承载所有明细。
DOCX output must follow this outline unless the user explicitly asks for a
summary only.
