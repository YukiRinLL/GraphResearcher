# Instruction-Residual Editing: LLM Agent 文档修改中的指令残留与原生化改写问题

更新时间：2026-05-03

## 0. 结论

这个问题值得研究，但不能只停留在“某个 prompt 里出现了几句不自然的话”。单独看“你的目标不是定义、维护或解释知识图谱结构……”这类句子，问题确实偏小，更像 prompt writing 的局部经验。

但如果把它扩展为一个更一般的问题，就有研究价值：

> 当 LLM agent 根据自然语言指令修改已有 prompt、规范文档、配置说明、API 文档或代码注释时，如何避免把“修改指令本身的语言结构、变更理由和排除项”泄露到最终 artifact 中，并让修改自然融入目标文档原有的体裁、风格和接口契约？

我建议把这个现象命名为 **Instruction-Residual Editing**，中文可以叫 **指令残留式改写**。

更精确的研究问题是：

> LLM agent 在执行编辑任务时，常常不是把用户意图抽象成目标文档中的自然表达，而是把用户指令改写成补丁式、迁移说明式、否定对比式文本。这会暴露修改来源，降低文档原生性，并可能改变 prompt/spec 的行为边界。

从 ICLR、ICML、NeurIPS 这类会议角度看：

- **不够强的版本**：只分析几个 prompt 里的“不自然句子”，这不够顶会，最多是经验博客或 workshop note。
- **可投稿的版本 A**：构建一个 benchmark，系统评估 LLM/agent 在真实文档编辑中产生 instruction residue、style drift、contract drift 的频率和影响。
- **可投稿的版本 B**：提出一种 artifact-native editing 方法，让 agent 先抽象编辑意图、识别文档体裁和保护区域，再生成无残留、局部化、契约保持的 patch。
- **更强版本**：benchmark + 方法 + 人类评价 + 下游 agent 行为实验，证明指令残留不只是“文风不好”，还会影响 prompt/spec 的可维护性、可审查性和执行行为。

一句话判断：

> 这个问题本身小，但它是一个更大问题的可观察症状：LLM agent 缺乏 artifact-native editing 能力，无法稳定区分“用户修改指令的语言”与“目标文档应该拥有的语言”。

## 1. Background

LLM agent 正在从一次性生成答案，转向修改真实工作区中的 artifacts：代码、prompt、README、schema、配置、设计文档、工作流说明和 agent 协议。SWE-bench 将真实 GitHub issue 转化为代码库修改任务，要求模型根据 issue 描述编辑代码。CanItEdit 等工作进一步关注“给定代码和自然语言编辑指令，模型能否正确修改代码”。PEER、EditEval、CoEdIT 则从写作和文本编辑角度研究模型如何根据指令更新已有文本。

这些工作共同说明：**编辑已有 artifact** 已经成为 LLM 的核心能力，而不只是生成新文本。

但现有评价大多关注以下问题：

- 修改后是否满足用户指令；
- 测试是否通过；
- 语义是否保持；
- 文本是否更流畅；
- 风格是否更一致；
- 模型是否遵守可验证指令。

它们较少专门研究一种微妙但常见的失败模式：**LLM 没有把编辑意图自然融入目标文档，而是把用户指令的语言痕迹保留在结果中**。

本仓库里的例子很典型。用户的原始意图是：

> 我会定义一个单独的 Graph Manager，来进行知识图谱的管理，你不需要在其他 agent 中定义知识图谱相关内容，他们只需要调取 Graph Manager 中的工具即可。

这条指令真正要求的是架构职责迁移：

- Searcher 不再定义图谱 schema；
- Searcher 仍然负责搜索、读取、抽取、分析；
- Searcher 把结构化结果提交给 Graph Manager；
- 图谱写入、去重、校验、查询等由 Graph Manager 负责；
- 原有输出协议和抽取要求应尽量保持兼容，除非显式要求迁移。

但 agent 修改后出现了类似句子：

- “你的目标不是定义、维护或解释知识图谱结构，而是把外部信息可靠地交给 Graph Manager……”
- “你是证据采集与抽取代理，不是图谱管理代理。”
- “不要在 prompt 内定义知识图谱节点、边或字段 schema。”

这些句子本身不一定错，但它们读起来像“刚刚根据一条迁移指令打上的补丁”。它们不是从新架构自然生成的角色说明，而像是把用户修改指令拆开后塞进了文档。

更自然的表达应该是：

```md
Searcher 负责围绕当前任务完成检索、来源读取、内容抽取、证据分析和结构化结果提交。所有来源、证据、事实、冲突和缺口信息均通过 Graph Manager 工具提交，并以 Graph Manager 返回的写入状态、对象 ID 和校验结果为准。
```

这段话表达了同样的职责边界，但没有显式暴露“这是从另一个文档迁移职责后补上的说明”。

## 2. Problem Definition

### 2.1 现象定义

给定原始 artifact `A`、用户编辑指令 `I`、上下文 `C`，LLM agent 输出修改后的 artifact `A'`。

我们关注的失败不是 `A'` 完全没有满足 `I`，而是：

> `A'` 满足了部分编辑意图，但把 `I` 的措辞、句法、对比结构、变更理由或排除项以不自然的方式残留在目标文档中，使修改结果显得像补丁、审稿回复或迁移说明，而不是目标 artifact 的原生内容。

可称为：

- instruction residue；
- edit-intent leakage；
- patch-trace language；
- non-native revision；
- 指令残留；
- 补丁痕迹；
- 变更来源泄露。

### 2.2 典型类型

**1. 否定对比残留**

典型句式：

```text
你不是 X，而是 Y。
不要做 X，由 Z 负责。
```

问题：它更像在纠正旧版本，而不是直接描述新版本职责。

**2. 指令转述残留**

用户说“你不需要定义知识图谱内容”，agent 直接写成“不要在 prompt 内定义知识图谱节点、边或字段 schema”。这类句子是用户指令的展开，而不是文档语言的重构。

**3. 迁移说明残留**

典型句式：

```text
现在由 Graph Manager 负责……
不再由 Searcher 维护……
```

如果目标文档不是 changelog 或 migration guide，这种“现在/不再”的历史感会暴露修改过程。

**4. 过度边界声明**

多次重复“不要定义 schema”“不要维护图谱状态”“不要替代 Graph Manager”，导致文档像规则补丁，而不是稳定角色规范。

**5. 风格断层**

原文是流程型、操作型、规范型，新插入内容突然变成纠偏型、警告型、否定型。读者能明显感知某几句来自一次外部修改。

**6. 隐性接口漂移的语言掩护**

agent 可能用更抽象的新句子替代旧结构，表面上更符合新要求，但实际上删除了原先的输出字段、证据要求或 workflow 细节。

### 2.3 与过度重写的区别

`idea.md` 已经讨论了 over-editing 和 scope control。`idea2.md` 关注一个更细的子问题：

- over-editing 关注“改得太多”；
- contract drift 关注“接口变了”；
- instruction residue 关注“文本像是根据修改指令硬塞进去的”。

这三者相关但不同。一个 patch 可以很小，却仍然有明显 instruction residue；一个 patch 可以很大，但如果重写后完全自然，也不一定有 residue。

## 3. Motivation

### 3.1 为什么它不是单纯的文风问题

在普通散文中，补丁痕迹会降低可读性。在 prompt、schema、agent 协议和设计文档中，它还有更实际的风险：

1. **行为边界被写成否定规则，增加模型误解概率**  
   Prompt 中反复出现“不要 X”，可能让模型在运行时过度关注被否定对象，甚至诱发不必要的规避行为。

2. **稳定规范变成迁移记录**  
   一个 agent prompt 应该描述当前角色，而不是解释它从旧架构迁移到了哪里。迁移语言会污染长期维护文档。

3. **review 成本上升**  
   人类 reviewer 需要判断这些否定句到底是必要规则，还是 agent 根据用户指令生成的冗余表述。

4. **隐藏更严重的 contract drift**  
   agent 用“交给 Graph Manager”这类概括句替换了具体字段和工作流，可能导致下游 Orchestrator/Reporter 失去可依赖的结构。

5. **多轮编辑会累积残留**  
   每次修改都把用户指令以补丁句形式塞入文档，几轮后 artifact 会变成一堆历史修改意见的混合体。

### 3.2 为什么适合扩展成顶会问题

顶会不太会接受“LLM 写得不自然”作为核心贡献，但会关注以下更一般的问题：

- LLM agent 如何维护长期 artifacts；
- agent 编辑是否可审查、可回滚、可组合；
- 自然语言规范如何在多轮修改中保持稳定；
- 文档型、prompt 型、schema 型 artifact 如何评价编辑质量；
- 模型是否能把用户指令抽象为目标文档的原生表达。

因此，研究焦点应从“这句话看起来像补丁”扩展为：

> Artifact-native editing under natural language instructions.

即：模型不仅要知道改什么，还要知道**修改后的内容在目标 artifact 中应该像什么**。

## 4. Challenge

### 4.1 Instruction residue 难以自动定义

“不是 X，而是 Y”有时是合理边界声明，有时是补丁痕迹。不能简单用关键词或否定句检测。需要判断：

- 这句话是否由用户指令直接转述而来；
- 它是否符合文档原有体裁；
- 它是否在该位置承担必要功能；
- 它是否可以被更原生的表达替代；
- 它是否重复说明了已经由结构表达的职责边界。

### 4.2 正确性与原生性是两个目标

一个编辑可能语义正确，但不原生。例如：

```md
你不是图谱管理代理。
```

语义上它表达了职责边界，但作为 Searcher prompt 的角色定义，它显得像外部纠偏。更原生的写法是直接描述 Searcher 的输入、处理和输出接口。

### 4.3 缺少可执行 oracle

代码可以跑测试，JSON 可以校验 schema，但 prompt 和设计文档的“自然融合程度”没有直接 oracle。需要结合：

- 人类标注；
- LLM judge，但要做校准；
- stylometric/genre consistency 特征；
- 指令-输出 lexical overlap；
- 下游 agent 行为模拟；
- contract extraction 和 diff analysis。

### 4.4 编辑目标本身往往欠规范

用户很少会说：

```text
请表达这个职责迁移，但不要使用“不是 X，而是 Y”这种否定对比句；
不要出现“现在由”“不再由”这类迁移痕迹；
保持原 prompt 的流程型写法。
```

这意味着模型需要从工程语境中推断隐含要求：最终文档应该像一个稳定规范，而不是一次修改记录。

### 4.5 多语言和领域风格差异

中文 prompt、英文 API docs、法律政策、科研 proposal、代码注释各自的原生表达不同。一个 residue detector 如果只学英文写作风格，很可能误判中文技术规范。

## 5. Related Work

### 5.1 Instruction-based text editing

PEER 提出协作式语言模型，关注写草稿、给建议、提出编辑和解释编辑行为。它的重要性在于把写作看成一个迭代修改过程，而不只是一次性生成最终文本。

EditEval 提出 instruction-based text improvement benchmark，强调现有文本的改进需要多种模块化编辑能力，例如更新信息、增强连贯性、改写风格。它还指出常用编辑指标之间相关性并不总是很好。

CoEdIT 通过任务特定指令微调来做文本编辑，覆盖简化、风格转换等用户指令，并展示了组合编辑指令的泛化能力。

这些工作与本问题直接相关，但它们主要评价“编辑是否改善文本”或“是否满足指定风格/属性”，较少评价“模型是否把编辑指令的语言结构残留进目标文档”。

代表性文献：

- Schick et al., 2022. PEER: A Collaborative Language Model. https://arxiv.org/abs/2208.11663
- Dwivedi-Yu et al., 2022. EditEval: An Instruction-Based Benchmark for Text Improvements. https://arxiv.org/abs/2209.13331
- Raheja et al., 2023. CoEdIT: Text Editing by Task-Specific Instruction Tuning. https://arxiv.org/abs/2305.09857

### 5.2 Instruction following evaluation

IFEval 关注可验证指令，例如字数、关键词出现次数等。它的贡献是把 instruction following 变成更可复现的自动评价。

但 instruction residue 不是简单的“是否遵守指令”。模型可能严格遵守了用户要求，却把指令写得太像指令本身。也就是说，本问题关注的是 instruction following 之后的 **artifact integration quality**。

代表性文献：

- Zhou et al., 2023. Instruction-Following Evaluation for Large Language Models. https://arxiv.org/abs/2311.07911

### 5.3 Code editing and agentic software engineering

SWE-bench 将真实 GitHub issue 转化为代码库编辑任务，推动了 repository-level agent evaluation。CanItEdit 专门评估 LLM 根据自然语言指令编辑代码块的能力，指出 instructed code editing 仍然研究不足。

这些工作说明“根据指令编辑已有 artifact”是重要能力，但它们主要依赖测试、参考补丁或代码行为验证。Prompt、规范文档和 agent 协议没有同样强的测试 oracle，因此更容易出现看似合理但长期有害的 residual edits。

代表性文献：

- Jimenez et al., 2024. SWE-bench: Can Language Models Resolve Real-World GitHub Issues? ICLR 2024. https://arxiv.org/abs/2310.06770
- Cassano et al., 2023. Can It Edit? Evaluating the Ability of Large Language Models to Follow Code Editing Instructions. https://arxiv.org/abs/2312.12450

### 5.4 Document-level editing and delegated workflows

DocMEdit 指出真实世界中存在 document-level editing，而不仅是短句或短事实编辑。DELEGATE-52 进一步从 delegated workflow 角度研究长文档编辑中的内容损坏问题，显示长交互、文档大小和干扰文件会加剧文档退化。

这些工作与本方向非常接近。区别是：

- DocMEdit 更偏 model editing 和文档级事实更新；
- DELEGATE-52 更偏长流程委托中的内容 corruption；
- instruction-residual editing 更关注“修改指令如何以语言残留形式进入最终 artifact”，尤其是 prompt/spec/config 这类文档即程序的场景。

代表性文献：

- Zeng et al., 2025. DocMEdit: Towards Document-Level Model Editing. https://arxiv.org/abs/2505.19572
- Laban et al., 2026. LLMs Corrupt Your Documents When You Delegate. https://arxiv.org/abs/2604.15597

### 5.5 Stylometry, AI-edited text, and writing homogenization

EditLens 研究 AI-edited text 的可检测性，并用相似性指标和回归模型估计文本中 AI 编辑的程度。关于 LLM 写作风格和 AI writing suggestions 的研究也显示，AI 可能使文本风格趋同，降低人类或文化表达的差异。

这些工作说明 AI 编辑会留下统计和风格信号。但 instruction residue 不是一般意义上的“AI 味”，而是更具体的编辑来源信号：最终文本中可以看出它是由某条修改指令派生出来的。

代表性文献：

- Thai et al., 2025. EditLens: Quantifying the Extent of AI Editing in Text. https://arxiv.org/abs/2510.03154
- Reinhart et al., 2025. Do LLMs write like humans? Variation in grammatical and rhetorical styles. https://arxiv.org/abs/2410.16107
- Agarwal et al., 2025. AI Suggestions Homogenize Writing Toward Western Styles and Diminish Cultural Nuances. https://arxiv.org/abs/2409.11360

### 5.6 Model editing locality

Model editing 领域长期研究 reliability、generality、locality 等概念：修改目标知识的同时，不破坏无关知识。虽然它编辑的是模型内部知识或行为，而不是外部文档，但 locality 思想可以迁移到 artifact editing。

对应关系：

- model editing 的 locality：无关模型行为不变；
- artifact editing 的 locality：无关文本、接口、结构和文档风格不变；
- instruction-residual editing 的 locality：用户指令语言不应泄露为目标文档中的非原生内容。

## 6. Research Gap

现有工作缺少一个直接研究以下问题的框架：

1. LLM agent 在编辑 prompt、spec、config、README、workflow 文档时，是否系统性产生 instruction residue？
2. 哪些类型的编辑最容易产生残留：职责迁移、边界收缩、安全规则插入、schema 抽象、模块重命名、删除旧能力？
3. 残留是否只是审美问题，还是会影响 human review、prompt execution、下游 agent 行为和长期维护？
4. 能否自动检测补丁痕迹，并区分必要边界声明与指令残留？
5. 能否设计 artifact-native editing agent，在保持任务成功率的同时降低 instruction residue？

一句话 gap：

> We can evaluate whether an edit follows an instruction, but we rarely evaluate whether the instruction has been naturally absorbed into the target artifact.

## 7. Proposed Benchmark: NativeEditBench

### 7.1 目标

构建一个 benchmark，评估 LLM/agent 在自然语言编辑任务中是否能生成 **artifact-native** 的修改结果。

核心评价对象不是普通流畅度，而是：

- 满足编辑意图；
- 不暴露用户指令语言；
- 保持目标文档体裁；
- 保持接口和结构契约；
- 修改范围最小充分；
- 无关内容不发生语义漂移。

### 7.2 数据来源

建议覆盖四类 artifact：

1. **Prompt/spec 文档**  
   multi-agent prompts、workflow prompts、tool protocol、system prompts。

2. **API/config 文档**  
   JSON/YAML schema、OpenAPI 说明、工具参数说明、CLI docs。

3. **工程文档**  
   README、design docs、architecture docs、migration docs。

4. **代码旁路文本**  
   docstrings、comments、error messages、user-facing copy。

Prompt/spec 文档应作为重点，因为这类 artifact 的文本本身会影响 agent 行为。

### 7.3 任务类型

- **Responsibility transfer**：把职责从一个 agent/module 迁移到另一个 agent/module。
- **Boundary refinement**：收紧角色边界，但保持原 workflow。
- **Schema delegation**：删除本地 schema 定义，改为调用外部 manager。
- **Safety constraint insertion**：加入安全规则，但不把文档改成警告列表。
- **Terminology migration**：替换概念名称，但保持原有结构。
- **Contract-preserving rewrite**：局部改写说明，但保持 JSON keys、API names、section hierarchy。
- **Style-native insertion**：插入新约束，但需匹配原文体裁和语气。

### 7.4 标注

每个样本包含：

- original artifact；
- user edit instruction；
- optional project context；
- target intent decomposition；
- protected spans；
- editable spans；
- preserved contracts；
- allowed new concepts；
- forbidden residual patterns；
- one or more human-written native revisions；
- residue span annotations；
- human preference labels。

### 7.5 负样本构造

可以构造三类负样本：

1. **Instruction-paraphrase negative**  
   把用户指令直接转述进文档。

2. **Patch-note negative**  
   用“现在由”“不再由”“从 X 改为 Y”这类迁移说明写正文。

3. **Over-boundary negative**  
   反复用“不要”“不能”“不是”强调排除项，使文档变成规则补丁。

这些负样本可用于训练 residue detector 或 preference model。

## 8. Metrics

### 8.1 Intent Success

判断目标编辑意图是否满足：

```text
IntentSuccess(A', I, C)
```

可由人类标注、LLM judge、schema checker、下游 simulation 组合完成。

### 8.2 Instruction Residue Score

衡量 `A'` 中有多少内容像是从 `I` 直接派生：

- lexical overlap with instruction；
- negation/contrast pattern frequency；
- migration-marker frequency；
- sentence-level entailment from instruction but not from artifact genre；
- human-labeled residue span ratio。

不能只用 overlap，因为必要术语会重合。例如 Graph Manager 这个名字必须保留。更合理的是识别“用户指令句法”和“修改理由句式”的残留。

### 8.3 Native Integration Score

判断新增或修改文本是否融入原文：

- section-level genre consistency；
- local style consistency；
- discourse role consistency；
- whether new text reads like stable documentation rather than edit instruction；
- human preference。

### 8.4 Contract Preservation

针对 prompt/spec/config：

- JSON keys 是否保持；
- tool names 是否保持；
- required output fields 是否保持；
- section hierarchy 是否无关漂移；
- downstream parser/simulator 是否仍可工作。

### 8.5 Minimal Sufficient Edit

changed lines 只能作为辅助指标。更核心的是：

- protected span preservation；
- unrelated semantic preservation；
- avoid unnecessary section deletion；
- avoid global style normalization；
- no unsupported abstraction。

### 8.6 综合指标

可以定义：

```text
NativeEditScore =
  IntentSuccess
  * ContractPreservation
  * NativeIntegration
  * SemanticPreservation
  - lambda_1 * InstructionResidue
  - lambda_2 * UnrelatedEditRatio
```

## 9. Proposed Method: Artifact-Native Editing Agent

### 9.1 Intent Abstraction

不要直接把用户指令写进目标文档。先把指令抽象成编辑义务：

```json
{
  "required_change": "Searcher submits graph-relevant extracted information via Graph Manager tools",
  "removed_responsibility": "Searcher does not define graph schema internally",
  "preserved_behavior": [
    "search",
    "read sources",
    "extract evidence",
    "analyze gaps and conflicts",
    "return structured status"
  ],
  "preserved_contracts": [
    "final JSON schema unless migration is explicitly requested",
    "task_id and search_task_id propagation",
    "failure reporting"
  ],
  "preferred_expression": "describe positive operational interface instead of using migration language"
}
```

### 9.2 Genre and Contract Extraction

修改前先抽取目标 artifact 的体裁和契约：

- 文档是 role prompt、workflow spec、migration note 还是 policy；
- 原文主要是流程型、规则型、解释型还是警告型；
- 哪些字段、工具名、section 是下游依赖；
- 哪些句式和术语是原文风格。

### 9.3 Patch Planning

生成 patch plan，而不是直接重写：

- 哪些段落需要修改；
- 哪些段落只需删去 schema 定义；
- 哪些职责应保留；
- 哪些输出字段不能改名；
- 新内容应以正向接口描述写入，而不是否定对比句。

### 9.4 Residue-Aware Generation

生成时加入约束：

- 避免“不是 X，而是 Y”，除非该句是目标文档原有风格或必要安全规则；
- 避免“现在由”“不再由”这类迁移痕迹；
- 避免把用户指令拆成多个 `不要` 列表；
- 优先使用目标文档已有结构表达新边界；
- 优先描述当前稳定职责，而不是历史变更。

### 9.5 Dual Verification

修改后使用两个 verifier：

1. **Intent verifier**：编辑意图是否满足。
2. **Native verifier**：是否存在指令残留、风格断层、迁移说明、无关抽象和 contract drift。

如果 Native verifier 失败，只修复被标记 span，不能重新生成全文件。

### 9.6 Preference Optimization

可构造 pairwise preference 数据：

- chosen：artifact-native revision；
- rejected：instruction-residual revision。

训练 residue-aware reranker 或用 DPO/RLAIF 优化编辑模型，使其偏好原生表达。

## 10. Experiments

### RQ1：指令残留是否普遍存在？

在多种 artifact 和编辑任务上测试主流模型与 agent scaffold，统计 residue span ratio、human preference 和 contract drift。

### RQ2：哪些因素诱发 residue？

变量包括：

- 指令是否以否定形式表达；
- 原文是否包含复杂 schema；
- 是否要求职责迁移；
- 是否使用全文件重写；
- 是否使用 patch-only editing；
- 上下文长度；
- 模型类型和 agent scaffold。

### RQ3：residue 是否影响人类 review？

让工程师或 prompt 作者比较两类 patch：

- 同样满足意图，但一个有补丁痕迹；
- 另一个为 artifact-native rewrite。

评估：

- review time；
- perceived maintainability；
- trust；
- willingness to merge；
- ability to identify true behavioral changes。

### RQ4：residue 是否影响下游 agent 行为？

对 prompt/spec 文档尤其重要。可以让修改后的 Searcher prompt 在模拟任务中运行，观察：

- 是否过度回避图谱相关抽取；
- 是否少返回证据结构；
- 是否把 Graph Manager 当成黑盒而丢失必要元数据；
- 是否输出字段漂移；
- 是否更频繁拒绝或降级。

这能把“文风问题”升级为“行为可靠性问题”。

### RQ5：Artifact-Native Editing Agent 是否有效？

与以下 baseline 比较：

- direct rewrite；
- diff-only prompting；
- plan-then-edit；
- self-refine；
- patch-only agent；
- contract-aware agent without residue detector；
- proposed artifact-native editing agent。

主要看：

- IntentSuccess 不下降；
- InstructionResidue 显著降低；
- ContractPreservation 提升；
- human preference 提升；
- downstream behavior 更稳定。

## 11. How to Expand the Small Problem

你担心它太小是对的。建议按以下路线扩展。

### 11.1 从“补丁句子”扩展到“编辑来源泄露”

单句补丁痕迹只是表象。更大的问题是：

> LLM 在编辑 artifact 时没有完成从 edit instruction 到 artifact-native expression 的语用转换。

这可以覆盖：

- prompt 修改；
- 法律条款修改；
- API 文档修改；
- 产品文案修改；
- README 修改；
- 论文 revision；
- 代码注释修改。

### 11.2 从“文风”扩展到“可维护性”

研究指标不要只问“自然不自然”，还要问：

- reviewer 是否更容易审查；
- diff 是否更容易 blame；
- 下游 parser 是否稳定；
- 多轮修改后 artifact 是否退化；
- prompt 行为是否漂移。

### 11.3 从“prompt editing”扩展到“documents-as-programs”

Prompt、workflow spec、config、schema docs 都是 documents-as-programs：它们看起来是自然语言文档，但会被机器、agent 或人类流程执行。

在这类 artifact 中，instruction residue 不只是不好看，而可能改变执行语义。

### 11.4 从“检测问题”扩展到“生成方法”

只做 detector 可能不够强。更好的论文结构是：

1. 定义问题；
2. 构建 benchmark；
3. 证明现有模型普遍失败；
4. 提出 artifact-native editing 方法；
5. 证明方法降低 residue 且不牺牲任务成功率。

### 11.5 从“单轮编辑”扩展到“多轮维护”

很多残留在单轮看不严重，但多轮会累积。可以设计 longitudinal benchmark：

- 对同一个 artifact 连续执行 10-20 个局部修改；
- 每轮都要求保持原生性和契约；
- 评估最终文档是否变成补丁说明集合。

这会和 DELEGATE-52 这类 delegated workflow 研究形成呼应。

## 12. Top Conference Positioning

### 12.1 ICLR / NeurIPS main track

需要强调模型能力和方法：

- instruction abstraction；
- genre-aware editing；
- contract-preserving generation；
- residue-aware preference optimization；
- agent scaffold 对编辑质量的影响。

只做现象观察不够。必须有方法贡献和跨模型实验。

### 12.2 NeurIPS Datasets and Benchmarks

如果主贡献是 NativeEditBench，适合 Datasets and Benchmarks track。要求：

- 数据来源真实；
- 标注协议严谨；
- 自动和人工指标可信；
- benchmark 能区分强弱模型；
- 有基线和错误分析；
- 数据许可清楚。

### 12.3 ICML

ICML 更偏方法和学习问题。需要把它形式化为 preference learning、constrained decoding、edit policy learning 或 multi-objective optimization。

### 12.4 ACL / EMNLP / CHI

如果研究重点放在写作、文档编辑、human review、协作写作体验，ACL/EMNLP/CHI 可能比 ICLR/ICML/NeurIPS 更自然。

### 12.5 风险

主要风险：

- 审稿人认为问题主观；
- novelty 被认为只是 text editing 的子问题；
- 自动指标不可信；
- 数据集规模太小；
- 没有证明 residue 影响实际任务；
- 方法只是 prompt engineering。

规避方式：

- 做真实 artifact benchmark；
- 做 span-level 人类标注；
- 做 downstream behavior experiment；
- 做多模型、多 scaffold 实验；
- 提供明确方法，不只是提示词模板。

## 13. Possible Paper Contributions

一个完整论文可以这样组织贡献：

1. **Problem**：提出 instruction-residual editing，定义 LLM agent 文档编辑中的指令残留问题。
2. **Benchmark**：发布 NativeEditBench，覆盖 prompt/spec/config/docs/code comments。
3. **Metrics**：提出 Instruction Residue Score、Native Integration Score、Contract Preservation 等指标。
4. **Analysis**：系统评估多个 LLM 和 agent scaffold，证明 residue 与编辑任务类型、指令措辞、上下文长度和工具接口相关。
5. **Method**：提出 Artifact-Native Editing Agent，通过 intent abstraction、contract extraction、patch planning、residue-aware verification 降低指令残留。
6. **Impact**：通过人类 review 和下游 prompt 行为实验，证明它影响可维护性和 agent reliability。

## 14. Minimal Viable Study

如果先做一个小规模原型，可以这样做：

1. 收集 100-300 个真实或半真实 prompt/spec/config 文档。
2. 设计 5 类编辑指令：职责迁移、边界收缩、schema delegation、术语迁移、安全规则插入。
3. 让多个模型生成修改。
4. 人工标注：
   - 是否满足意图；
   - 是否有 instruction residue；
   - residue spans；
   - 是否有 contract drift；
   - 哪个版本更像原生文档。
5. 做初步统计和案例分析。
6. 实现一个简单 residue-aware editing pipeline：
   - intent abstraction；
   - protected contract extraction；
   - patch generation；
   - residue critique；
   - span-level rewrite。
7. 比较 baseline 与 pipeline。

如果这个小实验能显示明显差异，再扩展成 benchmark paper。

## 15. 用当前例子重新表述研究动机

当前例子可以作为 paper introduction 的 motivating example：

> A user asks an LLM coding agent to update a Searcher prompt so that knowledge graph management is delegated to a separate Graph Manager. The desired edit is architectural: remove local graph-schema ownership while preserving the Searcher's evidence collection interface. The agent produces a revised prompt that satisfies the high-level request, but inserts patch-like sentences such as "you are not a graph management agent" and "do not define graph schemas in the prompt." These sentences are semantically related to the instruction, yet they read as residues of the edit request rather than native role specifications. Worse, the rewrite also compresses output fields and changes protocol names, suggesting that instruction residue often co-occurs with contract drift.

中文版本：

> 用户要求把知识图谱管理职责交给 Graph Manager。理想修改应当把 Searcher 的图谱相关职责改写为“通过 Graph Manager 提交结构化抽取结果”，同时保留搜索、读取、抽取、返回证据状态等协议。但 agent 生成了“你不是图谱管理代理”“不要定义 schema”这类补丁式句子。它们语义上接近用户指令，却不像目标 prompt 的原生职责描述。这说明模型没有完成从用户修改语言到目标文档语言的转换。

## 16. Final Recommendation

这个方向值得继续，但建议不要以“修改痕迹”作为论文标题或唯一问题。更强的定位是：

> Artifact-native editing for LLM agents: avoiding instruction residue while preserving intent, contracts, and maintainability.

如果你要做成顶会级工作，最稳的路线是：

1. 将“修改痕迹”定义为 instruction residue；
2. 将单点现象扩展为 artifact-native editing；
3. 构建 NativeEditBench；
4. 提出 residue-aware editing agent；
5. 用 human review + downstream behavior 证明它不是审美问题，而是 agent reliability 和 document-as-program maintenance 问题。

如果只想发 workshop 或短文，可以先做 empirical study：

> Do LLM agents leave instruction residues when editing prompts and specifications?

如果目标是 ICLR/NeurIPS 级别，建议标题更像：

> NativeEditBench: Evaluating Artifact-Native Editing in LLM Agents

或：

> From Instructions to Native Revisions: Reducing Edit-Intent Leakage in LLM Agent Workflows
