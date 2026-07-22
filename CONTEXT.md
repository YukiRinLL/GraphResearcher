# Research Lifecycle

这个上下文定义研究目标从证据收集到报告交付过程中使用的核心语言，避免把搜索终止与内容完整混为一谈。

## Language

**Must Objective**:
报告必须满足的证据合同，参与 Report Completeness 并约束报告授权。未满足时只能进入有限交付、预算耗尽或失败路径。
_Avoid_: Core Query、High-priority Detail

**Should Objective**:
不影响 Report Completeness 或报告授权的可选增强目标。它只能在不挤占 Must Objective 恢复工作的前提下继续，未完成时不会自动成为报告限制。
_Avoid_: Must Objective、Required Objective

**Blocked Objective**:
至少完成一次定向恢复后，当前有价值的恢复路径已经用尽，但证据合同仍未满足的研究目标。它是该目标搜索工作的终态，不表示内容完整，也不授权报告交付。
_Avoid_: Satisfied Objective、Completed Objective

**Report Ready**:
所有必需研究目标均已满足，并且研究组合已经稳定时，可以交付完整报告的状态。该状态优先于预算是否恰好同时耗尽。
_Avoid_: Limited Report Ready、Budget Exhausted

**Limited Report Ready**:
至少一个必需研究目标被阻塞，并且已经没有活动研究工作或需要先解决的致命冲突时，可交付明确披露缺口的有限报告。该状态不表示搜索预算已经耗尽，也不表示报告内容完整。
_Avoid_: Report Ready、Budget Exhausted

**Budget Exhausted**:
仍有必需研究目标未满足，并且搜索容量已经实际用尽时，只能交付有限报告的状态。
_Avoid_: Limited Report Ready、Report Ready

**Exhaustive Research**:
承诺满足全部必需研究目标、不能提前降级为 Blocked Objective 的研究范围。预算尚未耗尽但研究合同已经证明不可完成时，该研究失败而不自动交付报告。
_Avoid_: Bounded Research、Best-effort Research

**Report Completeness**:
必需研究目标相对于满足标准的加权完成程度，由每个目标的覆盖度与置信度中较弱的一项约束。它是只读的质量指标，不决定研究状态，也不授权报告交付。
_Avoid_: Report Readiness、Termination Score

**Report Delivery Mode**:
研究生命周期交给报告撰写者的交付合同，用于区分完整交付与有限交付，并携带实质性的证据缺口。内部停止原因不属于读者可见的报告内容。
_Avoid_: Stop Reason as Report Content

**Unmet Objective**:
证据合同尚未满足的研究目标，作为内部写作约束防止报告虚构、补齐或声称完整。它不是可以直接复制到正文的读者说明。
_Avoid_: Report Limitation、Reader-facing Disclaimer

**Substantive Uncertainty**:
与研究主题本身相关、并且有证据与来源绑定的不确定性。它可以用中性语言向读者披露，不包含搜索过程、预算或内部状态。
_Avoid_: Workflow Limitation、Stop Reason

**User Request**:
运行入口在任何模型调用前逐字保存的用户原始请求。它是 Reporter 唯一的写作要求来源，研究阶段可以从中派生检索目标和交付模式，但 Orchestrator 不得用摘要或转述替换它。
_Avoid_: Orchestrator Handoff Summary、Rewritten Request

**Criterion Satisfaction**:
一个 Query 的每条验收标准及其确定性校验结果。只有属于该 Query 评估子图、类型为 Claim 或 Evidence、并能追溯到带 URL 的 Source 的引用才能支持 `satisfied`；来源未提及或搜索无结果仍是 `unmet`。
_Avoid_: Coverage Summary、Search Miss as Evidence

**Query Reference**:
Reporter 工具用于定位 Query 的引用，只允许使用可读 handle。系统内部读取边界共享同一个无模型 resolver，并可处理完整节点 ID 或可唯一恢复的损坏前缀，但这些内部形式不得进入 Reporter 上下文或工具结果；未知或歧义引用必须报错，不能返回成功的空证据包。
_Avoid_: Best-effort Guess、Silent Empty Bundle

**Report Evidence**:
面向写作者的 Claim/Evidence 投影，保留正文、来源、置信度、限定条件、局限、定位信息和带 stance 的 Claim-Evidence 双向关系。它不包含 Analysis 节点，也不按 Query 状态向 Reporter 暴露研究过程。
_Avoid_: Atomic Fact Text Only、Orchestrator Analysis

**Report Chapter**:
Reporter 通过 `commit_report_chapter_batch` 保存的最新完整候选章节。候选正文无论验证结果都会落盘，并且是草稿组装、审查、修订和最终 Markdown 的唯一正文来源；只有全部确定性验证通过时才写入 ReportSection 与证据绑定。
_Avoid_: Rejected Draft Loss、Final-submit Section Copy、Parallel Draft Source

**Chapter-local Reference**:
Reporter-facing bundle 使用章节作用域内的 `e1`、`c1` 和 `x1` 引用 Evidence、Claim 与 Conflict，并通过 `bundle_token` 绑定到一次具体加载。Neo4j 节点 ID 只存在于系统侧 meta，不进入 Reporter 或 reviewer 上下文。
_Avoid_: Persistent Graph ID as Model API、Cross-chapter Reference Reuse

**Inline Citation**:
Reporter 在事实性段落或列表项的相应位置写入的 `[n]`。编号必须落在本章所选 Report Evidence 确定性推导出的 Source 集合内；编译器只校验和保留，不再给整章批量补同一组引用。
_Avoid_: Chapter-level Citation Cluster、Auto-appended Citation

**Report Review**:
完整候选稿生成后，由同一模型配置的独立低温实例执行一次只读语义审查。确定性问题与审查问题合并后最多触发一次章节修订；第二次提交无论验证结果如何都交付完整文件。只有确定性验证通过时才写入 Research Graph。
_Avoid_: Fact Research、Multi-round Editing

**Wikipedia Lead**:
Wikipedia 风格任务中唯一的 `section_type=lead` 章节。渲染时它紧跟文章标题且不产生 `## Lead` 标题，后续第一个正文 heading 位于 lead 之后。
_Avoid_: Lead Heading、Multiple Lead Sections
