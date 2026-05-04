# Intent-Preserving Agentic Editing: 研究 LLM Agent 修改任务中的过度重写与修改痕迹

更新时间：2026-05-03

## 0. 一句话结论

这个问题值得研究，但不能只以“Codex 类 agent 会留下修改痕迹”作为论文主题。若想达到 ICLR、ICML、NeurIPS 级别的发表标准，需要把它上升为一个更一般的问题：

> 当 LLM agent 在已有代码、prompt、配置或长文档中执行局部修改指令时，如何在满足用户意图的同时，最大化保持未授权区域的语义、接口契约和风格稳定？

更合适的研究命名包括：

- Intent-Preserving Agentic Editing
- Scope-Controlled LLM Editing
- Locality-Aware Agentic Modification
- Minimal-Sufficient Editing for LLM Agents

当前观察到的现象可以称为：

- over-editing：修改范围显著超过用户意图所需范围；
- contract drift：输出 schema、字段名、接口契约、prompt 协议等发生无授权漂移；
- modification trace：文本中出现明显的 agent 式重写痕迹，例如重复强调边界、统一改写术语、删除细节、过度抽象、格式重排；
- semantic collateral damage：目标修改完成了，但未要求修改的语义被损伤。

从顶会角度看，这个方向有潜力，但前提是论文必须提供：

1. 一个清晰、可复现、可量化的新任务或 benchmark；
2. 一组能捕捉“局部性、保持性、契约稳定性、任务成功率”的评价指标；
3. 一个比现有 agent/editing 方法更稳的技术方案；
4. 跨模型、跨 agent scaffold、跨文件类型的系统实验；
5. 人类标注或真实工作流数据支撑，证明这不是单个 prompt 的偶发现象。

如果只停留在 prompt engineering 或个案分析，更适合写技术报告、workshop 或软件工程会议短文；如果能做成 benchmark + method + analysis，则具备冲击 ICLR/NeurIPS Datasets and Benchmarks、ICLR main track、NeurIPS main track 或 ICML applied/agent evaluation 方向的可能性。

## 1. Background

LLM agent 正在从“生成一次性答案”转向“操作真实工作区”：读取仓库、搜索上下文、编辑文件、运行测试、提交补丁。SWE-bench 将真实 GitHub issue 转化为代码修改任务，强调模型需要在大代码库中理解 issue 并生成 patch；SWE-agent 进一步说明 agent-computer interface 会显著影响 agent 的代码导航、编辑和测试行为。AgentBench、MINT、ToolLLM 等工作也表明，工具调用、多轮交互、长期决策和 instruction following 是 agent 能否可靠工作的关键。

但现有 evaluation 大多关注“任务是否完成”：

- issue 是否 resolved；
- test 是否通过；
- function call 是否正确；
- benchmark score 是否提高；
- agent 是否到达目标状态。

在真实开发中，任务完成并不等价于修改质量高。一个 agent 可能通过测试，却引入不必要的大范围重写；可能满足用户的某条新约束，却破坏下游依赖的 JSON schema；可能把 prompt 中应保留的细粒度协议改写成抽象描述；也可能把“局部架构边界调整”执行成“全文件风格重构”。

本仓库中的例子正是这种失败模式：

- 用户意图：Searcher 不应定义知识图谱结构，只应调用 Graph Manager 工具；
- 原始文件：`src/prompts/searcher/zh/original_codex.md`，410 行；
- 修改后文件：`src/prompts/searcher/zh/codex.md`，235 行；
- 实际结果：删除了大量 schema 和字段细节，同时重写职责、工作流、输出 JSON 字段和命名。

这不是简单的“diff 变大”。核心问题是 agent 没有区分：

- 哪些内容是目标约束必须改变的；
- 哪些内容是支持目标约束但应该改写的；
- 哪些内容是下游协议，应该保持稳定；
- 哪些内容只是表述风格，不应被大规模清洗。

因此，prompt、配置、文档和代码都可以被看作“可执行规格”。对这些规格的编辑不仅要满足新意图，还要保持未授权语义和接口契约。

## 2. Problem Statement

给定一个已有 artifact `A`，一个自然语言修改指令 `I`，以及可选上下文 `C`，LLM agent 输出修改后的 artifact `A'`。传统评价只检查 `A'` 是否满足 `I`。我们关心更强的目标：

> 生成一个最小充分修改，使得 `A'` 满足 `I`，同时尽可能保持 `A` 中与 `I` 无关的语义、结构、接口和风格。

这个问题可以形式化为多目标优化：

```text
maximize   TaskSuccess(A', I, C)
maximize   SemanticPreservation(A, A', unrelated_to_I)
maximize   ContractPreservation(A, A')
maximize   StyleConsistency(A, A')
minimize   UnnecessaryEditScope(A, A')
minimize   ModificationTrace(A, A')
```

关键不是追求最短 diff。某些任务需要跨文件修改，短 diff 也可能是错误的。更合理的目标是 minimal sufficient edit：在满足用户意图和系统约束的前提下，只改变必要内容。

## 3. Why This Is Worth Studying

### 3.1 实用价值明确

真实 agent 工作流中，用户经常要求“改一处约束”“调整一个接口”“把某个职责迁移给另一个组件”。这类任务通常发生在：

- prompt engineering 和 multi-agent system 设计；
- schema、API、workflow 配置维护；
- 文档、README、设计文档更新；
- 前后端接口协议演进；
- 大型代码库中的局部 bug fix 或 feature patch。

过度重写会带来直接成本：

- code review 难度上升；
- 下游测试或解析器因字段漂移失败；
- 人类难以判断哪些改动是必要的；
- prompt 行为发生隐性变化；
- rollback 和 blame 变困难；
- agent 看似“完成任务”，实际留下维护债务。

### 3.2 学术空缺存在

已有代码编辑 benchmark 关注 debugging、translation、requirement switching、feature addition 等任务，但较少专门评估“未授权区域保持性”和“接口契约稳定性”。模型编辑领域长期关注 locality、specificity、generality，但对象是模型参数或模型行为；agentic editing 则是对外部 artifact 的局部修改，二者有相似目标，但评价对象和干预机制不同。

这为论文提供了一个自然切口：

- 借鉴 model editing 的 locality/specificity 概念；
- 借鉴 automated program repair 的 patch overfitting 和 patch correctness 问题；
- 面向 LLM agent 的真实文件编辑场景，提出新的 benchmark、metrics 和方法。

### 3.3 顶会审稿人可能认可的创新点

这个方向若做得好，不只是工程抱怨，而是 agent reliability 的核心问题：

- 当前 agent benchmark 的成功率无法反映编辑质量；
- 多轮 agent 和工具使用会放大局部指令到全局重写；
- LLM 的“helpfulness”倾向可能与 edit locality 冲突；
- 长上下文中的隐式契约很难被完整保持；
- prompt/doc/config 的错误不像代码测试那样容易暴露。

这类问题与 ICLR/NeurIPS 关注的 agent evaluation、alignment、tool use、long-context reasoning、LLM reliability 方向一致。

## 4. Challenges

### 4.1 用户意图边界是隐式的

用户通常不会明确列出“不许改哪些内容”。例如“不要在其他 agent 中定义知识图谱相关内容”隐含了：

- 删除或迁移 schema 定义；
- 保留 Searcher 的搜索、读取、抽取职责；
- 保持最终 JSON 协议尽量兼容；
- 不要重写整个 prompt 的风格和结构。

这些边界需要模型从上下文、项目惯例、文件结构和下游依赖中推断。

### 4.2 最小 diff 不等于正确编辑

简单用 edit distance、changed lines、changed files 作为惩罚会误伤必要的大修改。例如一次 API 迁移可能必须改多个文件。需要区分：

- textual minimality：文本改动少；
- semantic minimality：无关语义保持；
- behavioral minimality：运行行为不发生无关变化；
- contract minimality：schema、字段、接口、协议稳定。

### 4.3 Prompt 和文档缺少强 oracle

代码可以运行测试，但 prompt、设计文档和 agent 协议往往缺少可执行测试。即使 JSON schema 能验证，prompt 中的行为约束也很难自动判断。这要求结合：

- 结构化 diff；
- schema/interface extraction；
- LLM-as-judge，但需要校准；
- 人类标注；
- downstream simulation，例如让 Orchestrator/Reporter 调用修改后的 prompt 观察行为。

### 4.4 Agent scaffold 也是变量

SWE-agent 表明 agent-computer interface 会影响 agent 行为。对于本问题，编辑工具、patch 格式、上下文选择、计划机制、review loop、是否允许全文件重写，都会显著改变过度编辑概率。论文需要同时评估 base model 和 scaffold。

### 4.5 保持性与可读性存在冲突

有时 agent 重写全文会让语言更统一，但破坏审查和兼容性。研究需要明确偏好：在维护场景中，应优先保持契约和可追踪 diff，而不是追求全文件“看起来更干净”。

## 5. Motivation

一个强 motivation 可以这样表述：

> Current agentic coding benchmarks reward agents for reaching a target state, but under-specify the cost of collateral modifications. In real repositories, especially in prompts, configs, schemas, and documentation-as-specification, unintended edits can silently change system behavior while escaping tests. We need evaluation and methods for intent-preserving, scope-controlled editing.

中文版本：

> 现有 agent benchmark 主要奖励“把事情做成”，但真实工程更关心“只把该改的地方改对”。当 artifact 是 prompt、schema、配置或设计文档时，过度重写不会立刻触发编译错误，却会改变 agent 行为、破坏下游协议，并显著增加维护成本。因此，需要系统研究 LLM agent 的意图保持型编辑能力。

这比单纯说“agent 留下修改痕迹”更有学术力度，因为它连接了三个大问题：

- agent 是否真的理解用户意图；
- agent 是否能保持长期系统契约；
- agent evaluation 是否能覆盖真实维护风险。

## 6. Related Work

### 6.1 Agentic software engineering benchmarks

SWE-bench 提出从真实 GitHub issue 和 PR 构造软件工程任务，要求模型在代码库中编辑代码解决问题，并指出真实 issue 往往需要跨函数、跨类、跨文件理解和协调修改。这个 benchmark 推动了 agentic coding 的主流评价，但核心指标仍偏向 issue resolution 和测试通过，较少显式惩罚不必要的无关修改。

SWE-agent 进一步展示了 agent-computer interface 对 agent 的文件导航、编辑和测试能力有显著影响。这对本研究很重要：过度编辑不只是模型问题，也可能由编辑接口和 scaffold 诱发。

AgentBench 从多种交互环境评估 LLM-as-Agent，指出长期推理、决策和 instruction following 是可用 agent 的主要障碍。MINT 关注多轮工具交互和语言反馈，说明单轮能力不能直接代表多轮 agent 表现。这些工作支持一个判断：agent 的真实失败模式必须在交互环境中评估，而不能只看单次生成。

代表性文献：

- Jimenez et al., 2024. SWE-bench: Can Language Models Resolve Real-world Github Issues? ICLR 2024. https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html
- Yang et al., 2024. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. https://arxiv.org/abs/2405.15793
- Liu et al., 2024. AgentBench: Evaluating LLMs as Agents. ICLR 2024. https://arxiv.org/abs/2308.03688
- Wang et al., 2024. MINT: Evaluating LLMs in Multi-turn Interaction with Tools and Language Feedback. ICLR 2024. https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a0d3ae989a382ce6e50312bc35bf7e1-Abstract-Conference.html

### 6.2 Instructed code editing

CanItEdit、CodeEditorBench、EDIT-Bench 等工作开始直接评估 LLM 根据自然语言指令编辑已有代码的能力。CodeEditorBench 覆盖 debugging、translation、polishing、requirement switching；EDIT-Bench 强调真实用户指令、代码上下文、光标位置等因素。

这些工作与本方向最接近，但仍有差距：

- 多数任务聚焦代码，不覆盖 prompt、schema、配置和设计文档；
- 多数指标强调任务正确性，不充分衡量 contract drift 和 modification trace；
- 编辑任务通常有测试或 reference solution，而 prompt/doc editing 缺少强 oracle；
- 对“过度重写但语义看似合理”的失败模式关注不足。

近期的 benchmark audit 也指出，现有 instructed code-editing benchmark 的任务分布、语言覆盖、测试覆盖和真实部署代表性仍有限。这说明“编辑能力评价”本身仍是开放问题。

代表性文献：

- Cassano et al., 2023. Can It Edit? Evaluating the Ability of Large Language Models to Follow Code Editing Instructions. https://huggingface.co/papers/2312.12450
- Guo et al., 2024. CodeEditorBench: Evaluating Code Editing Capability of Large Language Models. https://arxiv.org/abs/2404.03543
- Chi et al., 2025. EDIT-Bench: Evaluating LLM Abilities to Perform Real-World Instructed Code Edits. https://arxiv.org/abs/2511.04486
- Ebrahimi and Rajbahadur, 2026. Edit, But Verify: An Empirical Audit of Instructed Code-Editing Benchmarks. https://arxiv.org/abs/2604.05100

### 6.3 Tool use and function calling

ToolLLM/ToolBench 关注 LLM 使用真实 API 完成复杂指令，BFCL 等 function calling benchmark 关注函数选择和参数正确性。这些工作与本研究的联系在于：如果 agent 在修改 prompt 或 schema 时改动了工具协议，可能导致 function calling 或 tool routing 失败。

本研究可以把 tool schema、JSON 输出格式、agent protocol 视为 contract，并评估 agent 编辑是否保持这些 contract。

代表性文献：

- Qin et al., 2024. ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs. ICLR 2024. https://proceedings.iclr.cc/paper_files/paper/2024/hash/28e50ee5b72e90b50e7196fde8ea260e-Abstract-Conference.html
- Berkeley Function Calling Leaderboard. https://sky.cs.berkeley.edu/project/berkeley-function-calling-leaderboard/

### 6.4 Model editing: locality, specificity, generality

MEND、ROME、MEMIT 等 model editing 工作试图修改模型中的特定知识或行为，同时保持其他行为不变。它们的对象是模型参数或模型行为，但其中的 locality/specificity/generality 思想非常适合迁移到 agentic artifact editing。

对应关系：

- model editing 的 reliability：目标事实是否被成功更新；
- agentic editing 的 task success：用户指令是否被满足；
- model editing 的 locality/specificity：无关事实是否保持；
- agentic editing 的 preservation：无关文件、字段、行为协议是否保持；
- model editing 的 generality：等价改写或相关 query 是否也生效；
- agentic editing 的 robustness：同类局部指令、不同项目风格下是否稳定。

代表性文献：

- Mitchell et al., 2022. Fast Model Editing at Scale. ICLR 2022. https://openreview.net/forum?id=0DcZxeWfOPt
- Meng et al., 2022. Locating and Editing Factual Associations in GPT. NeurIPS 2022. https://proceedings.neurips.cc/paper_files/paper/2022/hash/6f1d43d5a82a37e89b0665b33bf3a182-Abstract-Conference.html
- Meng et al., 2023. Mass-Editing Memory in a Transformer. ICLR 2023. https://openreview.net/forum?id=MkbcAHIYgyS
- Zeng et al., 2025. DocMEdit: Towards Document-Level Model Editing. ACL Findings 2025. https://arxiv.org/abs/2505.19572

### 6.5 Self-refinement and reasoning-action agents

ReAct 和 Self-Refine 代表了通过推理轨迹、行动和自反馈提升 LLM 输出质量的方向。它们说明迭代和反馈可以提升任务表现，但对本问题而言，简单 self-refine 也可能放大重写倾向：模型在“改得更好”的反馈循环中，可能继续清洗、重排和抽象原文，进一步损伤 edit locality。

因此，本研究可以提出 locality-aware refinement：每一轮 refinement 不只问“是否满足目标”，还要问“是否引入了无关变化”。

代表性文献：

- Yao et al., 2023. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023. https://openreview.net/forum?id=WE_vluYUL-X
- Madaan et al., 2023. Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS 2023. https://proceedings.neurips.cc/paper_files/paper/2023/hash/91edff07232fb1b55a505a9e9f6c0ff3-Abstract-Conference.html

### 6.6 Automated program repair and patch overfitting

自动程序修复领域长期研究 patch overfitting：补丁通过已有测试，但不是真正正确的泛化修复。这个传统问题与 LLM agent 过度编辑存在结构相似性：

- APR 中，测试通过不代表 patch 正确；
- agentic editing 中，用户指令被表面满足不代表修改安全；
- 两者都需要检测 collateral damage 和 under-specified intent。

区别在于，本研究的对象不局限于可执行代码，还包括 prompt、schema、配置、文档等弱 oracle artifact。

代表性文献：

- Le et al., 2018. Overfitting in Semantics-based Automated Program Repair. Empirical Software Engineering. https://ink.library.smu.edu.sg/sis_research/3986/
- Yu et al., 2019. Alleviating Patch Overfitting with Automatic Test Generation. https://arxiv.org/abs/1810.10614
- Ye et al., 2021. Automated patch assessment for program repair at scale. https://link.springer.com/article/10.1007/s10664-020-09920-w

## 7. Research Gap

现有工作缺少一个专门研究以下问题的系统框架：

1. LLM agent 在真实文件编辑中是否经常过度重写？
2. 过度重写是否会导致 schema drift、prompt behavior drift、工具协议漂移或 review 成本上升？
3. 哪些因素诱发该问题：模型、上下文长度、agent scaffold、编辑工具、prompt 结构、文件类型、指令措辞？
4. 如何自动判断某个 diff 是否是 minimal sufficient edit？
5. 能否设计 agent 方法，在不牺牲任务成功率的情况下显著降低 collateral edits？

一句话 gap：

> We have benchmarks for whether agents can edit, but not for whether they can edit only what should be edited.

## 8. Proposed Benchmark: ScopeEditBench

可以构建一个新 benchmark，暂命名为 ScopeEditBench。

### 8.1 数据来源

数据可以来自四类 artifact：

1. Prompt files：multi-agent prompts、system prompts、workflow prompts；
2. Config/schema files：JSON/YAML/TOML、tool schemas、API contracts；
3. Documentation-as-specification：README、design docs、protocol docs；
4. Code files：含有明确接口和下游测试的局部修改任务。

### 8.2 任务类型

- responsibility transfer：例如“知识图谱管理移交给 Graph Manager”；
- contract-preserving update：新增约束但不得改变输出 schema；
- terminology migration：局部替换概念，但保留结构；
- deprecation handling：移除旧模块职责但保留调用协议；
- safety constraint insertion：新增安全边界但不重写主流程；
- format-preserving edit：修改内容但保留 style/template。

### 8.3 标注内容

每个样本包含：

- original artifact；
- natural language instruction；
- relevant context；
- protected spans：不应修改的区域；
- editable spans：允许修改的区域；
- required semantic changes；
- forbidden changes；
- contract fields：必须保持的字段、函数、schema、工具名、JSON key；
- reference patch，可有多个；
- human judgement rubric。

### 8.4 评价指标

任务成功：

- instruction satisfaction；
- required change coverage；
- downstream test or simulation success。

保持性：

- protected-span preservation rate；
- contract preservation rate；
- schema/key stability；
- API/tool-name stability；
- semantic preservation score for unrelated claims。

过度编辑：

- unnecessary changed lines；
- unrelated edit ratio；
- moved/renamed section count；
- style drift score；
- modification trace score。

综合指标：

```text
IntentPreservingScore =
  TaskSuccess
  * ContractPreservation
  * SemanticPreservation
  - lambda_1 * UnrelatedEditRatio
  - lambda_2 * ModificationTraceScore
```

注意：changed lines 只能作为辅助指标，不能单独作为主指标。

## 9. Proposed Method

可以提出一个 Scope-Controlled Editing Agent，包含以下模块。

### 9.1 Intent Decomposition

将用户指令拆成：

- required changes；
- explicitly forbidden changes；
- inferred protected contracts；
- uncertainty points。

输出结构化 edit intent，例如：

```json
{
  "required_changes": [
    "Searcher must call Graph Manager instead of defining graph schema"
  ],
  "protected_contracts": [
    "final JSON top-level fields unless explicitly requested",
    "Searcher search/read/extract responsibilities",
    "tool failure reporting behavior"
  ],
  "editable_regions": [
    "Research Graph schema definition section",
    "Graph write workflow wording"
  ],
  "forbidden_changes": [
    "renaming output keys without downstream migration",
    "removing evidence extraction requirements"
  ]
}
```

### 9.2 Artifact Contract Extraction

自动抽取原文件中的契约：

- JSON schema and keys；
- tool names；
- section hierarchy；
- function/class signatures；
- required output format；
- cross-agent responsibilities；
- downstream references。

对 prompt 文件，可以抽取“行为契约”：

- agent role；
- allowed/disallowed actions；
- required output fields；
- workflow stages；
- failure handling rules。

### 9.3 Edit Planning with Protected Spans

在真正修改前生成 edit plan：

- 哪些 section 需要改；
- 为什么需要改；
- 哪些 section 必须保持；
- 预计 diff 范围；
- 是否需要同步下游文件。

### 9.4 Constrained Patch Generation

要求 agent 以 patch 为单位修改，而不是整文件重写。可以采用：

- span-level patching；
- AST/Markdown parser based edit；
- JSON/YAML structured update；
- schema-preserving rewrite；
- protected-span diff guard。

### 9.5 Locality-Aware Verification

修改后执行多层验证：

1. task verifier：目标约束是否满足；
2. contract verifier：schema、字段、工具名是否漂移；
3. preservation verifier：protected spans 是否被改；
4. trace verifier：是否存在大规模同义改写、风格清洗、无关重排；
5. downstream verifier：相关 agent 是否还能解析输出。

如果失败，要求 agent 只修复失败点，不能重新生成全文件。

## 10. Experimental Design

### 10.1 Research Questions

RQ1：主流 LLM agent 在局部编辑任务中发生 over-editing 的频率有多高？

RQ2：over-editing 与模型规模、上下文长度、文件类型、指令措辞、agent scaffold 是否相关？

RQ3：contract drift 是否能被普通测试捕捉？如果不能，哪些 verifier 最有效？

RQ4：Scope-Controlled Editing Agent 能否在保持任务成功率的同时降低无关修改？

RQ5：人类 code review 是否更偏好 minimal sufficient edit，即使全文件重写表面更统一？

### 10.2 Baselines

- direct rewrite：直接让 LLM 修改文件；
- diff-only prompting：要求输出 patch；
- plan-then-edit；
- self-refine；
- ReAct-style agent with tools；
- SWE-agent-like scaffold；
- proposed Scope-Controlled Editing Agent。

### 10.3 Models

应覆盖：

- frontier proprietary models；
- strong open-weight code models；
- general instruction models；
- small local models。

论文不应只比较一个模型，否则难以说明问题具有普遍性。

### 10.4 Evaluation

自动评价：

- unit tests / integration tests；
- schema validation；
- AST/Markdown structural diff；
- protected span matching；
- semantic similarity for unrelated regions；
- contract extraction consistency；
- LLM judge with calibration。

人工评价：

- edit necessity；
- reviewability；
- hidden behavior drift；
- whether the patch matches user intent；
- whether unrelated content changed。

### 10.5 Case Study

本仓库的 Searcher prompt 可以作为 motivating example，但不应作为唯一证据。可以放在 introduction 或 qualitative analysis：

- instruction only required moving graph schema responsibility to Graph Manager；
- actual edit reduced file from 410 lines to 235 lines；
- output schema changed from explicit `sources/documents/claims/evidence/triples/conflicts` to compressed summaries；
- `graph_write_status` became `graph_manager_write_status`；
- many detailed extraction requirements disappeared。

该例子展示了 contract drift、semantic collateral damage 和 modification trace。

## 11. Expected Contributions

一篇强论文可以声明如下贡献：

1. 提出 intent-preserving agentic editing 问题，系统定义 over-editing、contract drift、modification trace 等失败模式；
2. 构建 ScopeEditBench，覆盖 prompt、schema、配置、文档和代码的真实局部编辑任务；
3. 提出一组自动和人工结合的评价指标，衡量任务成功、语义保持、契约保持和过度编辑；
4. 系统评估多个 LLM 和 agent scaffold，揭示过度编辑的诱因；
5. 提出 Scope-Controlled Editing Agent，在保持任务成功率的同时显著降低 collateral modifications；
6. 发布数据、标注指南、评测脚本和 agent traces，支持复现。

## 12. Publication Strategy

### 12.1 ICLR / NeurIPS / ICML 主会

适合的定位：

- LLM agent reliability；
- instruction following under edit constraints；
- benchmark and evaluation；
- long-context artifact editing；
- tool-use agent safety。

需要强调 ML 贡献，而不只是软件工程经验：

- 新任务定义；
- 大规模系统实验；
- 可泛化方法；
- 对模型行为的分析；
- 可复现 benchmark。

### 12.2 NeurIPS Datasets and Benchmarks Track

如果 benchmark 质量高，这是最稳的顶会入口。需要：

- 数据来源真实、多样；
- 标注协议严谨；
- 自动指标与人工评价相关性高；
- baseline 覆盖充分；
- 数据和代码开放。

### 12.3 ICSE / FSE / ASE

如果技术实现和真实开发者 study 更强，而 ML 方法较弱，也很适合软件工程顶会。特别是 contract drift、patch reviewability、prompt-as-spec maintenance 这些角度，SE 社区可能更直接认可。

### 12.4 Workshop

早期版本可以投：

- ICLR/NeurIPS agent workshop；
- LLM for Code workshop；
- AI Agents workshop；
- Software Engineering for AI workshop。

## 13. Risks

### 13.1 审稿人认为问题太工程

缓解方式：不要只展示 anecdote。必须提出 formal task、benchmark、metric 和 method。

### 13.2 指标被认为不可靠

缓解方式：自动指标必须与人工评价做相关性分析；LLM judge 不能单独作为结论来源。

### 13.3 最小编辑偏好不总是成立

缓解方式：明确目标是 minimal sufficient edit，不是 shortest diff。允许必要的大范围修改，但要求说明和验证。

### 13.4 Prompt editing 被认为小众

缓解方式：把 prompt 纳入 broader artifact editing，包括 code、schema、config、docs。强调现代 agent 系统中 prompt 和 config 是 executable specification。

### 13.5 数据构造成本高

缓解方式：先构造中等规模高质量 benchmark，例如 300-800 个任务，而不是追求大而粗糙。顶会更看重标注质量和洞察。

## 14. Recommended Paper Angle

推荐标题方向：

> Agents Can Edit, But Can They Preserve? Benchmarking Intent-Preserving Edits in LLM Agents

核心摘要可以围绕：

1. LLM agents increasingly edit real artifacts;
2. Existing benchmarks reward task completion but ignore collateral modifications;
3. We define intent-preserving agentic editing;
4. We introduce ScopeEditBench;
5. We find frontier agents often over-edit prompts/configs/docs even when they satisfy the instruction;
6. We propose a scope-controlled editing framework that reduces contract drift and unrelated edits without hurting task success.

## 15. Minimal Next Steps

1. 收集 30-50 个真实案例，先验证 over-editing 是否普遍；
2. 设计 annotation rubric，区分 required/protected/optional edits；
3. 实现 diff analyzer，抽取 changed lines、section moves、schema key changes；
4. 设计 prompt/config/doc/code 四类 mini benchmark；
5. 跑 5-8 个模型或 agent scaffold；
6. 观察失败模式，决定方法重点是 planning、protected span、contract extraction 还是 verification loop；
7. 写 workshop paper 或 technical report；
8. 扩展到正式 benchmark paper。

## 16. Bottom Line

这个问题值得研究。它的价值不在于“某次 Codex 修改 prompt 留下痕迹”，而在于它暴露了 agentic editing 的一个未充分评估能力：在真实 artifact 中执行局部修改时，模型是否能保持未授权语义和系统契约。

顶会可发表性的关键是把现象抽象为可测任务，并证明：

- 这是普遍失败模式；
- 现有 benchmark 没有充分覆盖；
- 该失败模式会造成真实维护风险；
- 新方法能系统降低风险；
- 评价指标与人类判断一致。

如果按这个方向推进，它可以成为一篇关于 LLM agent reliability / editing evaluation / benchmark 的有竞争力研究。
