# 使用章节局部引用并保证报告交付

## 背景

报告契约 v3 要求 Reporter 把实际使用的 Claim/Evidence 节点 ID 原样提交给章节工具。一次同时加载多个章节时，模型能够理解所有证据内容，却难以持续记住数百个持久化 ID 分别属于哪个 bundle。严格校验会正确拒绝跨章 ID，但旧 middleware 没有 run 级失败预算，导致 Reporter 在首次有效提交前长期重试。

ms-agent v2 通过有限对话轮次、run 级反思计数和最佳现有文件提升来保证收敛，但其章节提交不校验证据是否属于当前 bundle。GraphResearcher 需要保留严格证据边界，不能直接采用这一宽松行为。

## 决定

新运行使用 `state_contract_version=4`。Reporter-facing 接口不暴露任何 Neo4j 节点 ID：Query 使用 handle，Evidence、Claim 和 Conflict 使用章节作用域内的 `e1`、`c1` 和 `x1`，引用登记使用 `[n]`。系统在章节 meta 中保存局部引用到节点 ID 的映射，并用 `bundle_token` 防止重新加载后的旧引用被误用。

Reporter 每批最多准备和提交三个章节。章节工具先保存完整候选正文，再执行引用和证据校验；失败只产生结构化 issues，不丢弃正文。首次最终提交执行一次 Review，并把确定性问题与 Review issues 合并；最多允许一次修订。第二次提交或 Reporter 到达运行上限时必须交付完整报告。

Reporter 第 20 次模型调用收到收敛提醒，第 24 次由 middleware 强制调用 `submit_final_report`。缺少候选章节时，系统从该章 bundle 的证据确定性生成保底正文。

## 影响

报告文件交付与图谱持久化分离。验证失败的报告仍写入 `report.md`，返回 `delivered=true`、`validated=false`、`graph_persisted=false`，并保留 validation warnings；只有确定性验证通过的最终章节才创建 ReportSection 和 Evidence/Source 关系。

v4 不兼容或迁移历史 outline、chapter meta 和 Reporter payload，也不修改已有输出目录或 Neo4j context。
