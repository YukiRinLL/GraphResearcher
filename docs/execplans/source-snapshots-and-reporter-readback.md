# 原文快照、Evidence 定位与章节回读

## 状态与目标

截至 2026-09-08，M1、M2、M3 分别提交为 `691dbdc`、`e69da52`、`b12a8f6`，分支为 `增加原文回放`。用户授权开始 M4 后，本轮已完成离线参数评估、历史材料统计和复现文档，修改保留在工作区。四个里程碑的离线实施范围已完成；真实模型的选择命中率和报告质量评估尚未执行。

目标是让 Reporter 能通过 Evidence 回到当次捕获的原文，在有界输入中补充必要上下文。原文保存在运行目录，Neo4j 继续保存图谱事实和定位关系。是否抽取发现事实、来源准入和 Claim 规范化不属于本次讨论范围。

## 已确认决策

1. 保留 Source → Document → Evidence 的证据层关系。Document 关联不可变原文快照，正文不整体写入图谱，也不为每个块创建图节点。
2. 保存 Tavily 实际返回的 `raw_content`，并在应用自身截断之前完成保存。快照表示本次捕获到的内容，不宣称覆盖网站完整原文。
3. `content` 用于筛选相关原文块。可精确匹配的片段定位到快照；摘要式内容只作为检索线索。不同 Query 的内容片段可以复用同一快照中的块。
4. 程序生成稳定块标识。既有 Analyzer 调用同时输出 Evidence 和 `block_refs`，程序验证定位，不增加独立的 LLM 定位调用。
5. 自动附带只选择本章相关 Evidence 直接定位的块，按章节目标分别排序和轮流分配预算。相同块去重，重复 Evidence 数量不作为重要性加分。
6. 程序使用相关性、正文增量、已有的限定或冲突关系进行初筛。它不保证理解新增文字的语义重要性，Reporter 负责判断是否需要回读。
7. 章节第一次调用可以直接返回完整章节，或批量提出原文阅读请求。最多执行一次回读，随后调用 Reporter 完成章节；不单独设置一个 LLM 阅读判断步骤。
8. 自动附带与主动回读共享原文预算。主动请求优先，可以替换自动附带材料；回读不触发新搜索。
9. 加载失败、定位失败和因预算未加载都应明确返回。未读取不能表述为已核实，材料不足时保留必要限定。

## 运行记录依据

两个 benchmark 目录共有 6 次运行、29 个归档章节材料包。根据 `evidence_ref_map` 回查图节点，单章 Evidence 数量中位数为 84，最大为 217；11 个章节至少有 100 条 Evidence。以 `o200k_base` 估算的候选 Evidence 与 Claim 正文合计中位数约为 6,019 tokens，最大为 15,334 tokens。

这些数值不包含完整指令、JSON 结构和关系元数据，也不等同于历史 API 的实际输入。旧运行没有完整原文快照，不能据此计算真实块去重率或断言长上下文造成了评分下降。

集成光子任务铌酸锂章节的 131 条 Evidence 只有 88 种完全不同的正文，其中一个文本出现 9 次。阴谋论任务的 5 个章节使用同一组 65 个候选节点。前者说明输入组装也需要去重，后者说明跨章节取材会重复产生费用；跨章节重复不等同于单次调用溢出。

每章新增原文 2,000 tokens 是此前提出的初始试验参数，不是运行记录证明的最优值。还应检查完整 prompt 的预算余量，为输出预留空间。

## 实施前的代码与目标差异

| 入口 | 实施前行为 | 所需变化 |
| --- | --- | --- |
| `src/tools/search_tools.py` 的 Tavily 调用边界 | 在返回上层前截断 `raw_content` 至约 20,000 字符 | 在该截断之前保存快照，并记录实际搜索阶段 |
| `src/agents/searcher.py` | 对来源再次截断；Analyzer 只接收 `raw_content`；组装 packet 时只转发现有字段 | 传入来自快照的带标识块，转发经验证的定位元数据 |
| `src/prompts/analyzer.md` | 不允许输出 `block_refs` 等额外字段 | 仅调整输入与定位输出契约，保持事实抽取规则 |
| `src/agents/memory_manager.py` | 用 `document_summary` 创建 Document，尚未转发快照和块引用 | Document 保存快照关联，Evidence 保存位置引用 |
| `src/tools/graph_tools.py` | `create_document` 每次新增节点；Evidence 的 key 包含 Document 和旧 locator | 首版只增加可选定位字段，不静默改变图节点去重身份 |
| `src/tools/report_tools.py` | 按 Query 持续翻页取得候选材料，以节点 ID 去重 | 另建章节共享原文视图，控制加载预算 |
| `src/agents/reporter_workflow.py` | 章节结果只接受 `chapters`；失败最多尝试 3 次 | 增加一次有界回读分支，区分回读与错误重试 |
| `src/tools/graph_manager_tools.py` 的 `configure` | 绑定图 context 并清理本轮报告产物 | 同时绑定快照根，保留既有清理范围 |
| Searcher 的结果规范化与 packet 合并 | 多次重建字段字典 | 逐层转发程序生成的捕获引用；M1 只转发到搜索结果，不改变 Analyzer 或入库 packet |
| Reporter 的 `_writer_chapter_bundle` | 再次投影为最小写作视图 | 显式投影阅读能力、已加载块和读取结果 |
| `tests/replay_reporter_workflow.py` | 新目录中回放旧图，没有快照配置 | 后续显式绑定来源运行的只读快照根，将报告和审计写入回放目录 |

当前 `CLAUDE.md` 中 JSONL 主存储和早期脚手架描述已落后于代码。本计划遵循 `AGENTS.md` 和当前 Neo4j 实现。

## 数据形状与接口

快照存储与捕获接口已在 M1 实现，图字段和 Analyzer 块阅读已在 M2 实现。Reporter 自动附带、预算控制与一次回读已在 M3 实现。

### 快照与捕获记录

本次运行目录下使用 `source_snapshots/` 保存正文、块索引和捕获记录。快照索引包含 `schema_version`、`snapshot_id`、`source_key`、`body_sha256`、`chunker_version` 和 `blocks`；每个块包含 `block_id`、`kind`、`start_char`、`end_char`，以及必要的结构依赖块引用。

M1 使用 `source_snapshots/snapshots/<snapshot_id>/body.txt`、同目录下的 `index-v1.json` 和 `source_snapshots/captures/<capture_id>.json`。`snapshot_id` 由来源身份和 UTF-8 正文字节哈希派生；`capture_id` 为每次实际响应中的每条结果单独生成。块标识采用 `<snapshot_id>:v1:b000001`，由原文顺序确定。未来分块版本使用新的索引文件，旧索引不覆盖。来源身份复用当前 Searcher 的 URL 规范化函数；不能规范化的 URL 保留原值作为捕获身份，不改变后续来源过滤。

正文以 UTF-8 保存，偏移采用解码后 Python 字符串的零起点、左闭右开区间。保存的正文不为去噪而改写；检索规范化在派生视图中进行，需要精确定位时维护到原文的映射。块标识由快照、分块版本和位置确定，不能仅以块文本哈希表示，因为同一段文字在一页中可能重复出现。

文件读写保留 CRLF 等原始换行。先原子发布完整正文，再原子发布索引；索引是快照可读取的完成标记。已存在文件必须与预期字节一致，损坏时报告失败，不覆盖。不同写入者可以复用同一份有效文件。孤立正文不是可读取快照，后续相同捕获可以补齐缺失索引。

快照身份由来源身份和完整捕获正文的精确哈希派生；同一运行中相同来源、相同正文复用快照，正文变化创建新版本。捕获时间、Query、原始 URL、实际搜索深度、返回的 `content`、供应商和应用截断信息单独记录，不能把多次检索的片段拼成一份不存在的原文。同文跨站转载也不能丢失各自来源身份。

捕获记录包含 `schema_version`、`capture_id`、`snapshot_id`、`chunker_version`、`context`、`query_id`、`search_run_id`、实际查询文本、结果位置、URL、标题、发布日期、`content`、捕获时间、供应商、响应 request ID、实际 cascade 阶段、请求参数和捕获状态。未显式指定深度时保存 `provider_default`，不推断供应商实际采用的深度。`application_truncated` 表示应用是否将要裁剪返回正文；供应商未说明网页覆盖情况时，`provider_completeness` 为 `unknown`。完整保存返回字符串不代表完整抓取网页。

搜索结果的程序字段 `source_snapshot` 返回 `stored`、`unavailable`、`error` 或 `disabled` 状态及可用的捕获引用。缺少运行根时禁用捕获；缺少正文时记录不可用。没有字典结果的响应也保存一次阶段记录，`result_index` 为 `null`，捕获状态放在响应顶层。供应商返回的 `raw_content_truncated` 原值另存为 `provider_raw_content_truncated`，不将其解释为网页完整性证明。文件或索引保存失败只影响捕获状态，不进入 Tavily 的搜索失败分支。捕获记录本身无法写入时在日志中报告失败，并保留返回状态。

优先按 Markdown 标题、段落、列表和表格边界分块。普通长段落可按句界细分，表格保持完整表头和必要脚注。结构依赖的识别属于程序能力范围，无法可靠拆分的超长单元保留整体并允许报告预算不足，不能假定程序能识别所有语义限定。

M1 的 v1 分块识别 ATX 标题、段落、列表、围栏代码和 Markdown pipe table；连续表格及紧随的显式 Markdown 脚注保持整体，块记录所属标题的 `dependency_refs`。普通段落以 2,000 字符为软目标按句界分组；无法安全拆开的长句、列表、代码或表格保留整体。空白分隔仍完整保存在正文中，索引无需为纯空白建块。程序不承诺识别所有表格脚注、跨段限定或网页结构。

### 图谱定位

Document 增加可选 `snapshot_id`、`chunker_version` 和 `capture_id`；原有 `text` 继续保存概述。Evidence 增加可选 `block_refs: list[str]` 和 `location_status`，由 Document 解析所属快照。正文和块索引仍在文件中，图属性不保存嵌套块对象。身份、版本和定位状态由程序生成，模型只选择已展示的块标识。

第一版不复用旧 `locator` 承载新结构，也不改写现有 `evidence_key` 规则。多个 Document 可以关联同一快照，从而先完成正文复用与章节去重；跨 Query 合并 Document、Statement 或 Evidence 节点属于另一个改造范围。

Analyzer 只能选择本次实际提供给它的块标识。程序校验标识所属快照和输入集合；普通摘录可进一步验证原句位置。表格整理形式允许只有经验证的块引用，不伪造逐字字符区间。块存在的校验不等同于证明 Evidence 被该块语义支持。

定位失败时保留原有可接受的 Evidence，清除不可用引用并记录失败，不新增定位修复 LLM 调用。历史 Evidence 没有定位字段时作为不可回读的旧记录处理。该策略不把位置校验升级成新的事实准入门槛。

`location_status` 使用 `valid`、`missing` 和 `invalid`，分别表示非空引用全部通过校验、未提供引用和引用校验失败。任一引用非法时清空该条定位集合，细节留在审计中；`valid` 不代表语义核实。旧记录缺少字段时不迁移。更新已有 Evidence 时，缺省定位字段不能清除已存在的有效位置。

### Analyzer 阅读视图

Analyzer 使用 `source.blocks` 阅读视图，其中每项包含 `block_id` 和来自快照的 `text`，并保留标题、URL、发布日期和捕获完整性标记。输出 Evidence 在现有 `local_ref`、`text`、`statement_refs` 上增加 `block_refs`。

先用 `content` 的精确命中形成候选，再结合 Query、`acceptance_criteria` 和 `research_goal` 进行本地词法排序，补齐结构并按原文位置展示。重复原句保留多个候选位置，搜索摘要只作为检索线索。M2 使用 20,000 字符正文上限，75% 用于定向相关块、25% 用于研究目标和分区覆盖，结构依赖也占用额度；该限制不宣称约束完整 prompt token。先按两部分额度选择，再把空闲额度依次借给剩余相关块和覆盖块。没有有效匹配时按首部正文和不同标题区域轮流选择，并明确只阅读了部分原文。

词法检索使用小写英文词项和中文双字片段，按词项集合重合度排序，不按 Evidence 重复次数加权。候选的精确片段命中优先，其次比较 Query／完成条件／`content` 的词法相关度和研究目标相关度，最后按原文位置稳定排序。分区覆盖按所属标题分组，研究目标相关的分区优先，各分区轮流选择。过大的结构单元保留整体并跳过，全部候选都无法容纳时退回现有有界正文输入，明确标记不可定位。

`source.reading_coverage` 说明实际阅读模式、选择范围和不可用原因；块视图不附带完整未选中索引。程序在单来源调用内保留已展示块集合，校验完成后只将 Document 的三个快照字段及 Evidence 的两个定位字段转发到入库 packet。选择范围、定位失败原因和可精确匹配的原句字符区间进入既有 `extraction_log`，不新增图属性。普通摘录无法逐字匹配时仅记录 `not_exact`，结构引用可仍为 `valid`；表格整理不被迫伪装成逐字摘录。

启用块视图后只展示 `source.blocks`，不重复附带同一正文的 `raw_content`；快照不可用时保留有界旧正文输入并标记不可定位。抽取规则不变不意味着抽取结果不变，必须用 fixture 检查发现事实的覆盖情况。

### Reporter 阅读视图与返回值

Evidence 阅读项增加可回读引用，章节增加共享的 `context_blocks`。每个已加载块带有块标识、关联 Evidence 引用和来源信息，原文只出现一次。未加载标识按需紧凑表示，所有标识、状态和结构开销也计入输入预算。

Evidence 的 `block_refs` 表示已公开的直接定位，`readable_block_refs` 表示可读的直接定位及一跳结构依赖或紧邻块。两者只公开预算容纳的子集，省略块引用的请求仍指向该 Evidence 的完整直接定位集合。首版不公开整页索引。自动附带仍只取直接定位集合，必要的表格结构在分块和定位阶段保持完整；主动请求可使用已公开的可读集合。同一快照的相同块去重，不合并不同来源的归属。

直接完成时继续接受现有的 `{"chapters": [...]}`。提出回读时，接受以下互斥结果：

```json
{
  "read_requests": [
    {
      "evidence_ref": "e12",
      "block_refs": [],
      "purpose": "核对该指标的实验条件与测量口径"
    }
  ]
}
```

`evidence_ref` 必须属于当前章节材料包；未指定块时读取该 Evidence 的定位块。显式块引用只能取自该证据的合法定位或已经展示的结构邻接索引。阅读目的用于审计和续写，不通过另一轮 LLM 转化为检索计划，也不开放任意文件路径或网络地址。

程序在每项请求的 `results` 中逐块返回 `block_ref` 和 `loaded`、`unavailable`、`invalid_ref` 或 `budget_exceeded` 状态，以表达部分加载成功。显式请求块优先，剩余预算再容纳自动选择块；保留原有 Evidence 和 Claim。第二次输入重新组装，不携带被替换原文的完整历史消息，避免名义上替换、实际上仍占上下文。

第二次正常调用只接受最终章节。最终提交工具、章节文件和来源引用编号继续使用现有 shape；阅读请求不作为章节提交，不创建新的研究事实。首版回读用于解释、条件核对和已有证据的上下文，不把读到的无关新命题自动视为已有 Evidence 支持；新增事实的证据绑定另行讨论。

## 预算与错误边界

自动选择按章节目标分别进行词法相关性排序，优先考虑相对已附带文字的增量，再参考图中已经存在的限定或冲突关系。各目标轮流选择；同一个块可以服务多个目标但只计一次。重复 Evidence 的数量和短文本本身不构成优先级。

排序按相关性、可计算的文字增量、已有 `qualifies`／`contradicts` 关系依次比较，同分按快照和位置稳定排序。过大块跳过后继续尝试其他候选并记录原因，不阻塞其他章节目标。文字增量不是语义重要性的证明。

新增材料预算默认每次章节输入 2,000 tokens，包含新增字段、结构、请求结果和正文；不是两次调用合计的费用上限。实际额度取增量预算与完整 prompt 剩余空间的较小值，后者扣除输出预留和安全余量。每次调用前重新计算完整序列化输入，未知模型需明确 tokenizer 口径和上下文上限。基础材料已超限时记录 `base_prompt_over_budget`，走既有章节失败路径，不删除 Evidence，也不反复发送相同超限输入。

章节局部状态使用 `model_invocations`、`failed_attempts` 和 `readback_used`。最多累计 3 次模型、结构或提交失败，允许一次不计失败的合法阅读请求；正常路径调用 1 次或 2 次，工作流层最多调用 4 次。首次有效阅读决策可在 JSON 错误后的重试中发生。非法 JSON、互斥分支同时出现、空请求数组或字段类型错误属于结构失败；合法请求中的越界引用、文件不可用或预算不足返回逐项结果并消耗唯一回读机会。回读后再次请求阅读属于协议失败。读取后的所有重试沿用替换视图，回读机会不重新开放。

4 次上限不包含 SDK 内部 HTTP 重试，大纲和全文润色也单独统计。当前模型工厂配置了自动重试，不能把工作流调用次数直接解释为实际网络请求次数。

读取失败不触发网络重抓、额外搜索或自动 LLM 修复。快照文件路径由当前运行根和受校验标识派生；切换运行时同时切换快照根，不能跨 context 查找碰巧同名的文件。图清理保持现有语义，不默认删除不可变运行产物。

M1 保证同一运行的并发捕获和顺序切换运行的隔离。当前图工具使用进程级 context，本轮不扩展为同进程多研究任务并行。Searcher 在调用边界绑定 Query 和 SearchRun 元数据，Tavily 的公开工具参数保持不变，绑定在退出或异常后恢复。

## 非目标与行为不变量

- 保持现有来源准入、事实抽取范围、Claim normalization、Query 状态机、收敛规则和搜索预算语义。
- 保持 Neo4j 为图谱事实来源，JSONL 为导出格式；快照是与图关联的运行文件，不作为另一套图数据库。
- 不对旧运行补抓网页来伪造历史快照，不迁移或删除既有图节点。
- 不全量附带原文，不引入向量库、嵌入调用或单独的 LLM 检索重排器。
- 保持章节并行分支的阅读状态隔离，某章回读不能改变其他章的预算或引用表。
- 保留最终提交的 Evidence 引用和引用编号规则，不能用原文回读绕开报告交付路径。
- 所有来自网页的文字保持数据身份，不作为 Analyzer 或 Reporter 的流程指令。

## 里程碑

### 里程碑 1：快照保存与分块基础

新增 `src/memory/source_snapshots.py`，将身份计算、分块和索引构造放在纯函数中，将文件写入、读取和哈希校验留在边界。通过现有运行配置明确快照根，在 Tavily 返回的正文被应用截断前捕获快照。保留当前 Searcher 与 Analyzer 的文本输入行为，暂不接入图字段或 Reporter 阅读。

存储入口为 `save_snapshot(root, source_key, body)`，读取入口为 `read_snapshot(root, snapshot_id, chunker_version="v1")`，返回原始正文和校验后的索引；失败通过文件异常或 `ValueError` 暴露。`build_snapshot_index` 是纯函数。`configure(output_dir, context)` 只绑定配置、不创建或清理文件；`search_capture_scope(query_id, search_run_id)` 用 `ContextVar` 在搜索调用期间固定配置并恢复归属。`capture_source` 负责异常降级和捕获记录。Tavily 工具签名保持不变。

捕获记录包含实际搜索阶段，因此 academic cascade 的每次实际返回应单独记录，不改变回退选择、搜索次数或日志中的正文裁剪策略。快照写入失败时记录明确失败状态，原有搜索继续；没有运行输出根时不写入共享工作目录，明确标记捕获未启用。

验收：大于 20,000 字符的 fixture 完整落盘；相同捕获复用正文而保留不同 Query 的观察记录；正文变化产生新快照；重复段落有不同位置标识；中英文偏移能精确回切原文；并发写入不会留下部分文件；不同运行互不读写；本阶段模型调用数和 Analyzer 输入不变。

### 里程碑 2：Evidence 定位与图谱关联

接入 Document 的快照引用、Evidence 的块引用和定位状态。更新 Searcher 的选择视图、Analyzer 的输入输出、packet 转发、MemoryManager 入库和图工具的可选字段。选择和回退参数使用本计划的 Analyzer 阅读视图约定。

`src/memory/evidence_locations.py` 提供纯函数 `select_source_blocks`、`validate_block_refs` 和 `quote_locations`；`source_snapshots.load_captured_snapshot` 负责文件与归属校验。Searcher 单次调用后将程序计算的阅读和定位诊断合并到 `extraction_log`，MemoryManager 复核搜索归属后转发可选字段，图工具再校验 Document／Evidence 来源与当前图 context。旧调用不提供新字段时不读取快照，Reporter 的材料投影和提交路径保持原有行为。

M2 在读取捕获记录时核对当前快照根、context、来源 URL、快照身份及分块版本。Searcher 与 MemoryManager 还核对 Query 和 SearchRun 归属，避免把其他搜索的捕获误绑到本轮 Document。模型返回的身份和定位状态不被采信。入库边界复核来源及快照归属，定位失败只清除新增关联或块引用，不改变原有事实绑定和 SearchRun 状态机。无定位字段的旧调用不触发快照读取，也不新增默认定位属性。

验收：模型返回的块引用只允许来自其输入；普通原句位置可校验；表格整理不要求伪造精确摘录；多对多映射可读回；错误引用不能跨来源或运行；旧图仍可读取；同一来源仍只执行现有 Analyzer 调用。

### 里程碑 3：有预算的自动附带与一次回读

扩展章节准备视图和 Reporter 互斥返回协议。实现按目标轮流选块、共享块去重、token 预算、一次回读、替换后重新组装 prompt，以及不随错误重试重置的回读状态。更新 Reporter prompt，仅调整阅读与返回协议。

用户已确认默认应用预算为 32,768 tokens，输出预留为 8,192 tokens，安全余量为 1,024 tokens，原文增量为 2,000 tokens。这些值均通过配置调整，不代表供应商声明的模型容量。使用 tiktoken 按模型识别编码；默认 `gpt-5.1` 明确采用 `o200k_base`，与已安装 LangChain 的编码选择一致，其他未知模型必须设置编码名称。完整输入逐次计数，消息封装开销由安全余量覆盖；章节调用同时将输出预留设为模型的 `max_tokens`，大纲和润色调用保持原配置。所有新状态是章节临时编排状态，不新增图谱状态枚举。

每次回读最多接受 4 项请求，每项最多 4 个显式块引用，目的文字最多 200 字符。直接定位与一跳可读索引按剩余预算公开，未公开的显式引用不能使用；省略块引用仍可请求该 Evidence 的直接定位。请求结果优先占用增量预算，若连必要结果元数据也不能容纳，则记录 `source_context_metadata_over_budget` 并结束该章，不提交超限输入。旧 JSONL 不包含 context，回放只从明确指定的来源运行根读取 Document 指向的捕获记录，以该记录的原 context 校验关联，不扫描其他运行目录。

验收：有足够材料时章节正常路径不增加调用；回读只增加一次正常调用；错误重试不重开回读；请求结果逐项可审计；共享块不重复；替换后的输入没有旧块历史；多个章节状态隔离；最终提交、引用校验和 fallback 交付回归保持通过。

### 里程碑 4：离线验证与参数评估

M4 新增独立的离线评估入口、运行目录清单和结果说明，不调整生产配置、图字段或报告提交规则。比较 1,000、2,000、4,000 tokens 的原文预算，完整应用预算保持用户确认的默认值。使用固定日期模板和确定性模型响应替身，报告实际序列化 prompt 的 token 数、块与目标覆盖、未加载原因、工作流调用和失败次数。覆盖率按 fixture 预先标注的块—目标关系计算，不把词法命中或模型替身的章节保存结果当成报告质量。

使用保存的章节目标、Evidence 与构造的原文 fixture，测试重复、多目标覆盖、表格结构依赖和预算不足。记录实际 prompt token、选中块、未加载原因、回读次数和错误重试次数。旧 benchmark 可提供章节结构和材料规模，不能充当缺失快照的真实回读数据。

评估结果见 [章节原文预算的离线评估](../evaluations/source-context-budget.md)。33 组案例通过运行时预算、token 复核、引用绑定和调用上限检查；新增评估回归 10 项通过。历史记录中 29 章的 Evidence 数量和候选正文 token 统计已精确复现，默认参数保持不变。

真实新运行才能测量自动选择命中率和报告质量变化。需要端到端评估时单独说明模型与 Tavily 成本，不在离线验收中隐式执行。达到当前已授权里程碑后停止，不自动进入下一阶段。

## 兼容策略

新字段首版为可选，旧 Document 和 Evidence 正常提供原有写作材料，回读返回不可用。快照写入成功后才发布可读取索引；图中引用的文件丢失或校验失败时明确报告不可用，不自动改指向更新的网页。正文文件复用不意味着图节点或来源引用合并。

准备、校验、提交、组装和 `main.py` 交付路径均需纳入影响检查。首版不更改报告接受条件来迁就回读失败，也不删除旧回归断言。

阅读审计保存在独立的 `report_source_context/chapter-<id>/`，不修改现有章节提交文件结构。审计关联原 `bundle_token`，记录阅读视图、选择原因、逐块结果、tokenizer 与调用计数。回放显式读取来源运行的快照根，将新报告和审计写入回放目录；无快照时返回不可用，不搜索其他目录或联网补抓。只读回放不调用具有清理副作用的 `configure()`。

历史 benchmark 的统计以显式运行目录清单为输入，记录图、章节元数据和大纲的文件哈希。没有完整快照的历史运行只提供目标、Evidence 和材料规模；用于阅读参数比较的正文另行构造，并在结果中标明。

## 验证命令

里程碑 1 使用独立脚本 `tests/test_source_snapshots.py`；后续定位与选择测试可分别放入 `tests/test_evidence_locations.py` 和 `tests/test_report_source_context.py`。实施时沿用项目的裸包导入和 fixture／monkeypatch 模式，不依赖真实 Neo4j 或模型。

```bash
# 里程碑 1。
uv run python tests/test_source_snapshots.py
uv run python tests/test_tavily_searcher_pipeline.py
uv run python tests/test_graph_context.py

# 里程碑 2：覆盖现有入库约束。
uv run python tests/test_evidence_locations.py
uv run python tests/test_search_lifecycle.py
uv run python tests/test_graph_invariants.py
uv run python tests/test_contract_v3.py

# 里程碑 3：新增脚本后执行，并验证完整交付路径。
uv run python tests/test_report_source_context.py
uv run python tests/test_report_context.py
uv run python tests/test_reporter_workflow.py
uv run python tests/test_report_validation.py
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_report_delivery.py
uv run python tests/test_report_completeness.py
uv run python tests/test_reporter_replay.py

# 里程碑 4：输出目录必须尚不存在。
uv run python tests/test_report_source_context_eval.py
uv run python tests/eval_report_source_context.py --output-dir outputs/source_context_eval_m4_verified

# 每个实施里程碑检查实际改动，并记录仓库既有 lint 问题。
uv run ruff check src tests main.py test_wlc.py
```

## 执行记录

- 2026-09-08：整理已确认设计，检查搜索截断、Analyzer packet、图工具和 Reporter 章节路径。记录图节点身份、历史快照缺失及错误重试计数的边界。本次只新增计划文档，未修改运行时代码，未运行真实搜索、模型或数据库验证。
- 2026-09-08：用户授权新建分支开始修改。在 `codex/source-snapshots-m1` 上补全数据身份、失败边界和后续阅读契约，本轮实施范围限定为 M1。
- 2026-09-08：完成 M1。新增 14 项离线回归覆盖长正文、CRLF／中英文偏移、重复段落、超长结构单元、正文发布后索引完成前的拒读、并发捕获、损坏校验、文件失败、运行切换、无目录禁用、级联空响应和查询清洗重试。比较启用与禁用快照时的完整 Analyzer 消息和入库 packet，两者一致。没有新增模型或搜索调用，没有修改图字段、来源过滤或 Reporter。
- 验证：`uv run python tests/test_source_snapshots.py` 通过全部 14 项检查；新增模块与新增测试的 Ruff 检查通过；`git diff --check` 通过。完整 `uv run ruff check src tests main.py test_wlc.py` 返回 209 项问题，与通过 `git archive HEAD` 提取的修改前代码相比，按文件、规则和信息统计没有新增问题。
- 既有回归：`tests/test_tavily_searcher_pipeline.py` 在第 249 行的来源数量断言失败，fixture 的短文本触发当前 `B_login_wall` 过滤；`tests/test_graph_context.py` 在第 255 行的路径断言失败，测试期待正斜线 context，当前规范化返回反斜线。两项均在临时目录的修改前 `HEAD` 上复现同样失败。本轮保留原断言和运行语义，用新增独立 fixture 验证捕获对模型输入、入库 packet 和运行根绑定的兼容性。
- 验证过程未访问真实 Neo4j、Tavily 或模型。M1 实现完成，M2—M4 尚未开始。
- 2026-09-08：M1 提交为 `691dbdc`。用户授权开始 M2，采用上述 20,000 字符与 75%／25% 初始选择参数；本轮不接入 Reporter 回读。
- 2026-09-08：完成 M2。新增 `tests/test_evidence_locations.py` 的 13 项检查全部通过，覆盖截断位置之后的精确匹配、中文词法检索、研究目标和分区覆盖、表格完整性、重复原句位置、未展示块及伪造模型元数据拒绝、快照缺失与超长单元回退、多对多入库、跨来源／Query／SearchRun 拒绝、同快照多 Document，以及旧调用保留已有定位。图测试只替换存储边界，实际执行 MemoryManager 和 Document／Evidence 创建函数，没有访问 Neo4j。
- M1 存储脚本的 14 项检查通过；其中原有 Analyzer 输入不变检查随 M2 的明确输入变更调整为块正文、调用次数与事实 packet 兼容检查，并明确断言新增字段和原有字段的取值。既有来源准入、引用绑定和状态机断言未放宽。
- M2 的 `test_search_lifecycle.py` 在第 220 行因旧 Evidence 的 Statement 引用不符合当前校验而失败；`test_graph_invariants.py` 在第 62 行因当前 Query 转换采用容错处理而失败；`test_contract_v3.py` 在第 235 行因当前审阅流程与旧预期不同而失败。三项均通过临时目录提取提交 `691dbdc` 的源码复现相同结果，未修改这些回归脚本。
- 新增模块、快照模块及两份定位相关测试的 Ruff 检查通过，`git diff --check` 通过。完整 Ruff 检查仍为 209 项既有问题，与 `691dbdc` 相比没有新增。M2 验证未访问真实模型、Tavily 或 Neo4j；没有新增 LLM 调用，M3—M4 尚未开始。

- 2026-09-08：M2 提交为 `e69da52`。用户授权开始 M3，并确认 32,768／8,192／1,024／2,000 tokens 的应用预算、输出预留、安全余量和原文增量配置。
- 完成 M3。`report_tools` 在保持引用注册表与 `bundle_token` 的同时附带内部定位；新增 `report_source_context` 固定章节快照根、验证关联、选择直接定位块并公开有界的一跳索引。阅读请求与最终章节互斥，合法回读只消耗一次机会，读取和提交失败均不会重置；章节最多 3 次失败、4 次工作流模型调用。新 prompt 按一次模板替换组装，原文中的模板占位符保持原样。
- 阅读审计写入 `report_source_context/chapter-<id>/audit.json`。`views` 保存每次实际发给模型的原文视图、逐块预算结果及 token 数；`resolved_requests` 保存读取边界的结果，不能将其 `loaded` 直接视为已经展示，是否进入模型输入以对应 `views` 为准。审计还记录选择原因、配置、请求、调用和失败计数。审计写入失败只记日志。回放入口明确绑定来源运行的快照根，报告与审计写入新回放目录，不调用图谱清理配置。
- 新增 `tests/test_report_source_context.py` 的 24 项离线回归通过，覆盖自动附带、共享去重、来源身份、按目标轮选、超大块跳过、双重预算、必要元数据超限、输出上限、一次回读、非法分支、部分加载、缺失文件、提交重试、替换后没有旧块正文、跨运行隔离、真实回放入口的读写目录、并行章节隔离、旧图兼容和审计写入失败。
- 既有 `test_reporter_workflow.py` 的并发 fixture 原先按全局队列领取章节响应，token 计数改变线程调度后会将其他章节的响应错发给当前章节。现将三个并发用例的 fixture 改为按输入章节 ID 领取响应，保留全部调用次数、提交内容、并发度和降级断言；单章错误 ID 的回归仍按原顺序执行。
- 验证通过：`test_source_snapshots.py`（14 项）、`test_evidence_locations.py`（13 项）、`test_report_context.py`、`test_reporter_workflow.py`、`test_reporter_artifact_persistence.py`、`test_report_completeness.py` 和 `test_reporter_replay.py`。新增模块与测试及其他无既有问题的修改文件通过 Ruff，`git diff --check` 通过。
- 在 M3 修改前运行的 `test_report_validation.py` 已于第 104 行出现 `invalid_source_ids`／`no_valid_sections`；`test_report_delivery.py` 已于第 181 行因缺少 `e1` 失败。修改后复现同样结果，没有修改其断言或扩大引用与交付规则。完整 Ruff 检查为 209 项问题，使用 `git archive e69da52` 提取基线后按文件、规则和信息比较，没有新增问题。
- 本轮验证未调用真实模型、Tavily 或 Neo4j。M3 实现完成，M4 的参数和报告质量评估尚未开始。

- 2026-09-08：M3 提交为 `b12a8f6`。用户授权开始 M4，新增 `tests/eval_report_source_context.py`、显式历史目录清单及 `docs/evaluations/source-context-budget.md`，没有修改生产代码、默认参数或图谱契约。
- M4 完成 8 个构造案例和 3 个历史材料规模案例，分别比较 1,000／2,000／4,000 tokens，共 33 组。完整应用预算沿用 32,768 tokens，输出预留 8,192，安全余量 1,024。固定模板时间、输入文件哈希及实现文件哈希，记录完整 prompt、审计、块选择、未加载原因、标注目标覆盖和调用计数。
- 从明确列出的 6 个运行目录读取 29 章，没有缺失映射节点；Evidence 数中位数 84、最大 217，11 章至少有 100 条 Evidence，候选正文 tokens 中位数 6,019、最大 15,334，精确复现原先观察。6 个目录均没有原文快照，评估用正文明确标为构造材料，没有将历史摘要当作实际捕获。
- 三个历史规模案例保留原章节大纲、候选正文及 Evidence—Claim 关系，引用和快照按 fixture 构造；没有将其作为历史 API 输入重建。最大案例的构造基础 prompt 为 35,659 tokens，超过 23,552 tokens 的输入上限，三档原文预算下均以零模型调用进入章节失败路径。较小案例可完成一次回读，多目标案例也显示选中目标集合不一定随预算单调扩大。本轮记录这些边界，保留 2,000 tokens 默认值。
- 完整矩阵输出位于 `outputs/source_context_eval_m4_verified/`，共 51 次确定性响应替身调用、6 次注入失败，全部检查通过；没有真实 API 请求或模型费用。新增评估回归 10 项通过，覆盖统计分母、缺失输入、材料重复、结构完整性、预算替换、错误计数、同输入复现、配置恢复、来源只读和输出防覆盖。
- `test_report_source_context.py` 的 24 项回归、`test_reporter_workflow.py` 和 `test_reporter_replay.py` 通过。两个新增评估文件的 Ruff 检查及 `git diff --check` 通过，完整 Ruff 仍为 209 项既有问题。M4 离线验收完成；本轮未执行真实 Neo4j、Tavily、模型或质量评分。
