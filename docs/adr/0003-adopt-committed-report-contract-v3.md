# 采用以原始请求和已提交章节为核心的报告契约 v3

## 背景

旧报告链路会在初始化和 Orchestrator 交接时多次转写用户请求，Reporter 最终只能依赖压缩后的研究目标。Query handle 在读取证据包时可能静默失效，Report Evidence 丢失认识论字段，最终提交又允许传入一份独立的 sections，使章节草稿、最终正文和图谱绑定发生漂移。引用编译器还会把章节的全部来源附到每个无引用段落，形式上增加引用数量，却削弱了事实与来源之间的对应关系。

## 决定

从新运行开始写入 `state_contract_version=3`。入口在任何模型调用前逐字保存 User Request，`init_research()` 只从 run context 读取原文；Reporter 直接接收这份原文和派生的 Delivery Mode，Orchestrator 的 handoff 不再携带事实摘要、章节建议或实体判断。

Query 持久化逐条 `criterion_results`。一次 Query assessment 同时判断全部 criterion，系统随后校验 supporting refs 是否属于当前 Query 的 Claim/Evidence、是否能追溯到带 URL 的 Source。只要关联 Query 仍有未满足 criterion，Objective 就不能标记为 satisfied。

Reporter 先加载章节证据包，再通过 `commit_report_chapter` 只提交正文和实际使用的 Evidence ID。系统从这些 Evidence/Claim 推导 Source 集合并校验正文中的 `[n]`。已提交章节成为大纲组装、候选稿、审查、修订、最终 Markdown 和 ReportSection 绑定的唯一正文来源；`submit_final_report()` 不再接收 title 或 sections。

确定性校验通过后，独立低温 reviewer 最多运行一次。它不能搜索或修改正文；发现问题时只允许 Reporter 进行一次简单章节重写，第二次提交不再复审。reviewer 异常时记录 attempt artifact 并交付确定性有效的原稿，不把审查结果写入 Research Graph。

Wikipedia 风格任务必须且只能有一个 lead。编译器把 lead 直接放在文章标题后，不输出 lead heading，并统一在末尾生成唯一的 References 区域。

## 影响

新运行不兼容旧字段、旧 outline 或 `submit_final_report(sections=...)`，也不迁移或删除历史 Neo4j context、`outputs/` 和 JSONL。每份报告正常路径最多增加一次模型调用；criterion 判断继续复用已有 Query assessment 调用。实体身份消歧、Analysis provenance、逐事实 block schema、来源排名和多轮报告审查留待后续设计。
