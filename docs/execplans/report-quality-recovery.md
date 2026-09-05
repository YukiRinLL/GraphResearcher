# 报告引用与研究覆盖改进

## 状态与目标

本文件是待用户确认的方案草案，尚未授权实施任何里程碑。每次只实施用户明确确认的里程碑，验收后停止。

以 `outputs/wlc_tavily_baseline_18/reporter_replays/52-Archaeology_of_North_Korea-20260905-163742` 为诊断样本，分别处理章节引用映射错误、来源抓取异常、研究覆盖失衡和报告篇幅分配问题。历史报告与评测结果保持原样，新实验使用独立目录和评测 agency。

## 已确认的现有约定

- Neo4j 仍是图谱事实来源，JSONL 用于快照与重放。
- Reporter 使用章节局部 Evidence、Claim 和 Conflict 引用，并以 `bundle_token` 绑定证据包。
- 章节并行执行，候选正文保留；单章失败不取消其他章节，仍交付可获得的完整报告。
- 全文经过一次润色；润色调用失败时交付确定性组装稿。
- 初始发现 Query 保持精简，后续研究通过 Objective 和 Gap 扩展。

这里记录的是现有行为，不表示用户已批准下述修改。

## 诊断依据与待验证边界

- 墓葬章将 `e10`、`e12`、`e13`、`e14` 等局部 Evidence 编号直接写成数字文献引用。章节 meta 已记录引用校验失败。
- 当前工作流明确允许章节校验失败后继续交付；修复方案不能把这个既有选择误当成未经设计的异常。
- 评测抓取的一个 PDF 实际为浏览器拦截页，却因正文超过 100 字符被作为有效来源。两个明确抓取失败的来源则使 36 条事实跳过引用评估。
- 本次研究图缺少若干文化分期与机构史的主干材料，Reporter replay 无法自行补足。
- 当前完整度公式将 coverage 与 confidence 分别按阈值归一化后截断到 1；已有测试明确允许 coverage=0.8、confidence=0.75 得到 1。因此本次 1.0 不是已经证实的算术错误，必须先改善目标粒度与证据评估。
- 当前大纲和润色 prompt 允许的结构编辑范围比旧 `parallel-reporter-polish.md` 更广。实施时保留用户当前工作区的结构编辑能力，不按旧计划回退。

## 非目标

- 不恢复多轮独立语义审查，不改为校验失败就取消整篇报告。
- 不修改 NodeType、EdgeType、Query 状态枚举或 Neo4j 迁移策略。
- 不将参考维基条目及其事实列表注入研究或写作流程。
- 不通过调整评审标准、允许平局或修改事实支持定义提高分数。
- 不同时更换模型、提高搜索预算或改变完整度公式，避免无法归因。
- 不改写现有运行产物，不回退当前工作区已有修改。

## 里程碑 1：由程序将证据引用转换为文献引用

### Proposed shape

章节模型的 JSON 键继续使用 `chapter_id`、`content`、`evidence_refs` 和 `disclosed_conflict_refs`。修改 `content` 的引用语法：模型使用 `[@e10]`，需要多个证据时使用 `[@e10][@e12]`；Claim 通过关联 Evidence 引用，正文不使用 `[@c1]`。

章节模型的 Evidence 投影保留 `ref`、`text`，不再暴露 `source_numbers`。来源映射继续保存在程序侧，以 `bundle_token` 和章节 meta 中的 `evidence_ref_map` 解析。现有图谱节点和内部证据包可以保留 `source_numbers`，无需迁移。

程序在章节提交边界将每个 Evidence 标记转换为该 Evidence 对应的、经过 URL 去重的来源编号，再保存现有章节 Markdown。全文组装仍负责统一编号和参考文献区，润色模型仍接收普通 `[n]` 引用。

新增 `.report_chapters/chapter_XX.candidate.json` 保存模型原始候选，供解析失败后的诊断；现有 `chapter_XX.md` 继续是组装和交付的唯一章节正文来源。章节 meta 新增 `citation_format`，新路径明确写入 `evidence`，缺省按旧 `numeric` 路径读取。格式由调用程序指定，不根据正文猜测，也不要求模型新增字段。

### 行为边界

- 仅在当前 bundle 中存在、类型为 Evidence、且与本次提交选择一致的标记可以解析。跨章节、过期或未知 ref 均不得转换为一个看似合法的来源编号。
- 新格式正文中的裸数字引用不能作为旧格式自动放行，避免重新引入 `e10` 与 `[10]` 混淆。
- 引用标记无法解析属于候选格式错误，使用既有章节尝试上限反馈重试，不增加预算。原始候选仍落盘；重试耗尽后使用已存在的可编译候选，若没有则沿用确定性章节补齐。单章问题不取消其他章节或最终完整交付。
- 其他语义校验问题继续按现有直接交付策略处理；候选可保存、引用可编译、语义通过必须分别表达，不能互相替代。
- 组装时合并各章既有 issues，避免最终记录只剩“越界编号已删除”的信息；不改变 `success`、`delivered` 和 `validated` 的既有含义。
- 润色结束后增加一次无模型的参考文献一致性检查：来源编号与 URL 映射、文献顺序保持一致，正文只使用有效编号。失败时记录 issue 并交付组装稿，不再调用润色模型。
- 这个检查不能证明润色没有把有效引用移动到错误事实，也不能证明 Evidence 与正文语义一致；这些限制保留在验收说明中。

这是章节正文语法、内部模型输入、候选持久化和局部失败处理的契约变更。润色后的确定性检查也是对旧计划“暂不检查润色输出”的明确扩展，须随本里程碑一起确认。

### 影响面与兼容

涉及 `reporter_workflow.py`、`report_tools.py`、`graph_manager_tools.py`、`reporter.md`、`reporter_polish.md` 和 Reporter 回归脚本。检查 middleware 与 `main.py` 的最终读取路径，但保持最终交付 payload 和 Markdown 格式不变。旧数字引用章节与旧 replay 继续按旧格式加载，不能重新解释其中的 `[10]`。

### 验收

- 使用真实错误模式构造隔离 fixture：`e10` 对应来源 2，而来源 10 也合法存在。新路径必须生成来源 2 的引用，不能误指来源 10。
- 覆盖多 Evidence 同一来源去重、一个 Evidence 多来源、过期 bundle、跨章 ref、未知 ref 和裸数字引用。
- 失败重试有界，原始候选保留，完整报告仍可交付，最终 issues 不丢失。
- 润色改变来源 URL 或产生未知编号时回退组装稿；正常润色不增加模型调用。
- 旧产物加载、并行顺序、润色超时和最终交付路径继续通过回归。

## 里程碑 2：隔离评测来源抓取异常

此里程碑位于相邻 `Wiki_Live_Challenge` 仓库，须单独确认并先读取该仓库的协作规则。

保留现有抓取字段和支持率公式，改进正文有效性识别：浏览器错误页、访问挑战和只有登录提示的页面不得因长度足够而成为有效正文。判定同时依据页面结构与错误特征，避免一篇正常文章因为讨论访问限制而被误判。

对失败来源进行有界重试。只有可以证明是同一文献的直接 PDF 或官方镜像才作为恢复路径；文章中附带的其他链接不能自动替代原来源。保留原引用 URL，并在抓取结果中新增可选 `resolved_url` 和 `fetch_status`，旧数据缺省继续兼容。

评测摘要保留现有字段，新增 `citation_evaluation_coverage = evaluated_statements / total_statements`，并报告抓取失败、无有效引用等跳过原因。无法抓到正文的事实保持未评估，不直接记为事实错误。

验收使用本次拦截页和空正文 fixture；既有已判为无效的来源仍无效，正常正文不误伤。新评测单独输出，旧指标不被覆盖；明确报告分母变化，不将覆盖率下降伪装为支持率提高。

## 里程碑 3：用现有 Objective 表达主题主干

保留当前 Objective 字段和 discovery-first 查询模式，调整目标规划与组合评估：百科任务的必需维度分别成为有可验收标准的 Objective，不能把整个主题压缩成一个宽泛目标。维度从用户请求和主题知识结构提取，首次发现搜索用于校正术语并生成独立研究 Gap；不固定使用本题的维度，也不把规划假设当作证据。

本题的验收 fixture 至少区分考古文化分期、学科发展史、机构与出版物、解释与争议。每个目标按其自身相关证据评估；同一来源可以支持多个目标，但曼月台材料不能因为数量多就替代机构史或文化分期证据。

沿用现有 must/should、criterion_results、Gap 和有限交付机制。缺少主干证据时，生成或保留相应 Gap；某一分支阻塞不自动证明对应目标完成。先改进目标与证据的匹配，不修改 completeness 公式、搜索预算、停止状态和 recursion guard。

此阶段修改规划和覆盖判断规则，须单独确认。若 fixture 证明必须改变 Query 状态机或停止规则才能满足要求，应记录差异并提出后续方案，不能在本阶段顺手扩大范围。

影响面为 `memory_manager_prompts.py`、`memory_manager.py` 及 Objective、portfolio、convergence 回归脚本。旧图谱不重新拆分目标；改进只作用于新研究，旧 replay 的证据边界保持不变。

验收：只有曼月台证据时，其他主干目标仍未满足；机构史搜索失败不消失为“已覆盖”；初始单主题仍使用精简发现 Query。采用多个不同类型主题验证目标拆分，避免对单一 benchmark 题目过拟合。

## 里程碑 4：在完整材料上改善大纲与表达

保留大纲和润色 JSON shape，以当前 prompt 为基线进行局部修改。大纲根据主题主干安排结构与篇幅，将个案放入对应维度；同一材料多、Query 多不能成为独立长章的理由。对研究确实缺失的材料不虚构正文。

章节正文将必要限定放在对应事实附近，删除重复解释“不能证明什么”的泛化段落。润色继续允许删并章节、调整顺序和重写导言，但只能使用已有草稿事实，保留来源身份与必要限定。

本题期望的是文化分期、学科发展、机构、主要遗址与解释争议组成的均衡概述；不硬编码章节名称、案例篇幅百分比或最低词数。已有证据不足时不要求 Reporter 补出机构史。

验收先比较同一证据快照的 Reporter 输出，再比较使用新研究流程取得证据的输出。写作评分、引用质量和覆盖率分别报告，不预先承诺模型评审得分。人工核对主干覆盖、主题比例、重复段落和引用对应关系。

## 验证与实验顺序

实施前记录工作区现有差异和相关测试基线。旧 ExecPlan 中记录的失败不视为当前事实，需要重新确认；不得通过放宽断言消除无关失败。

第一阶段运行相关独立脚本：

```bash
uv run python tests/test_report_validation.py
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_workflow.py
uv run python tests/test_reporter_replay.py
uv run python tests/test_report_delivery.py
uv run ruff check src tests main.py test_wlc.py
git diff --check
```

第三阶段增加：

```bash
uv run python tests/test_report_completeness.py
uv run python tests/test_marginal_portfolio.py
uv run python tests/test_blocked_objective_convergence.py
uv run python tests/test_convergence_livelock.py
```

先完成离线回归，再在单独确认模型/API 成本后开展实验：固定证据重放验证引用改进；固定报告重新抓取验证评测修复；最后新建 context 验证研究覆盖。各实验使用独立输出目录和 agency，保持模型配置与搜索预算一致，每次只改变一个因素。涉及相邻仓库的具体测试命令在该里程碑开始前补入本计划。

## 建议确认范围

首轮建议只确认里程碑 1。里程碑 2、3、4 保持待讨论，不随首阶段自动启动。里程碑 1 主要解决可定位的引用映射错误，不承诺显著改善维基事实覆盖率。
