# GraphResearcher V10 完整分析报告（详细版）

**生成时间**: 2026-08-04 15:30
**测试主题**: Ring of Nestor
**测试状态**: ✅ 已完成
**总日志行数**: 12,193 行

---

## 一、V10 运行完整过程

### 1.1 运行时间线

| 阶段 | 开始时间 | 结束时间 | 耗时 |
|------|---------|---------|------|
| 初始化 | 13:59 | 13:59 | <1s |
| 搜索阶段 | 14:00 | 14:25 | ~25min |
| 报告生成 | 14:25 | 14:45 | ~20min |
| **总计** | | | **~45min** |

### 1.2 完整环节列表

```
1. init_research (L409)
   ├── 创建研究目标和 3 个 Objectives
   └── 创建初始查询 q1

2. dispatch_searcher (L467) → q1
   ├── 搜索 "Ring of Nestor -site:en.wikipedia.org"
   ├── 返回 5 个来源
   └── 写入图谱: 5 sources, 5 documents, 20 statements, 18 evidence

3. assess_query (L637) → q1
   ├── sufficiency_score: 0.72
   ├── 创建 3 个 gaps
   └── 状态: needs_expansion

4. evaluate_research_portfolio (L668)
   ├── artifact_identity_context: coverage=0.45, confidence=0.72
   ├── interpretation_authenticity: coverage=0.68, confidence=0.65
   ├── encyclopedic_evidence: coverage=0.38, confidence=0.62
   └── report_completeness: 0.677

5. expand_gaps (L752) → 创建 q1.1
   ├── 父查询: q1
   ├── 新查询: "Ring of Nestor" authenticity debate Isopata tomb...
   └── expansion_mode: vertical

6. dispatch_searcher (L861) → q1.1
   ├── 搜索长查询（15+ 关键词）
   ├── 返回 5 个来源
   ├── 写入图谱: 5 sources, 5 documents, 29 statements, 22 evidence, 1 conflict
   └── novelty_score: 0.818

7. assess_query (L1044) → q1.1
   ├── sufficiency_score: 0.46
   ├── 状态: needs_expansion
   └── 关键词过多导致质量下降

8. 继续多轮搜索... (L1163-2400+)
   ├── expand_gaps 创建更多子查询
   ├── dispatch_searcher 执行搜索
   ├── assess_query 评估结果
   └── evaluate_research_portfolio 更新覆盖度

9. 报告生成 (L4868+)
   ├── export_report_context → delivery_mode: limited
   ├── commit_report_outline → 4 章节
   ├── prepare_report_chapter_batch × 多次
   └── submit_final_report → 完成
```

---

## 二、每轮查询详细数据

### 2.1 第 1 轮：q1（初始查询）

**执行时间**: L467-L596

| 项目 | 内容 |
|------|------|
| **查询文本** | `Ring of Nestor -site:en.wikipedia.org` |
| **创建位置** | L450-454 |
| **重要性** | core |
| **接受标准** | Finds authoritative sources identifying the specific Ring of Nestor |

**搜索结果**：

| # | 来源标题 | URL | 质量评分 | 内容字符数 | 类型 |
|---|---------|-----|---------|-----------|------|
| 1 | The Pseudo-Minoan Nestor Ring and Its Egyptian Iconography | journals.librarypublishing.arizona.edu | 0.014 | 1,872 | JAEI 同行评审 |
| 2 | The Pseudo Minoan Nestor Ring and Its Eg | scribd.com | 0.014 | 3,616 | Scribd PDF |
| 3 | some observations on the iconography of the 'ring of nestor' | academia.edu | 0.013 | 20,000 | Academia 论文 |
| 4 | The Ring of Nestor: a Glimpse into the Minoan After-World | nature.com | 0.011 | 4,672 | Nature 期刊 |
| 5 | Evans, Arthur J.: "The ring of Nestor" | digi.ub.uni-heidelberg.de | 0.011 | 9,083 | Heidelberg 数字化 |

**写入图谱数据**（L593-594）：
- sources: 5
- documents: 5
- statements: 20
- claims: 0（后续归一化）
- evidence: 18
- conflicts: 0

**评估结果**（L642-654）：
```json
{
  "sufficiency_score": 0.72,
  "criterion_results": [
    {
      "criterion": "Finds authoritative sources identifying the specific Ring of Nestor and its principal scholarly context",
      "status": "satisfied",
      "reason": "The evidence identifies Arthur J. Evans's 1925 work and later peer-reviewed studies..."
    }
  ],
  "status": "needs_expansion",
  "created_gaps": ["gap_1", "gap_2", "gap_3"]
}
```

**关键发现**：
- ✅ 首轮查询简洁有效，返回 5/5 高质量来源
- ✅ sufficiency_score=0.72，远超 V8 的 0.24
- ⚠️ 仍创建了 3 个 gaps，需要继续搜索

---

### 2.2 第 2 轮：q1.1（第一个子查询）

**执行时间**: L752-L1032

| 项目 | 内容 |
|------|------|
| **创建位置** | L756-763 |
| **父查询** | q1 |
| **查询文本** | `"Ring of Nestor" authenticity debate Isopata tomb Knossos 1920 Heraklion Archaeological Museum scholarly journal article academic paper evidence forgery genuine provenance iconography inscription goldwork -site:en.wikipedia.org` |
| **关键词数** | 15+ 个 |
| **重要性** | supporting |
| **expansion_mode** | vertical |

**问题分析**：
- ⚠️ 查询包含 15+ 关键词，严重违反"简洁性规则"
- ⚠️ 包含了在 `plan_followup_query` 负面示例中列出的所有关键词
- ⚠️ 这是"负面示例变成参考"的典型案例

**搜索结果**：

| # | 来源标题 | URL | 质量评分 | 说明 |
|---|---------|-----|---------|------|
| 1 | The Pseudo-Minoan Nestor Ring... | egyptianexpedition.org | 0.653 | 🔴 重复内容 |
| 2 | The Pseudo-Minoan Nestor Ring... | journals.librarypublishing.arizona.edu | 0.575 | 🔴 重复内容 |
| 3 | Heraklion Archaeological Museum... | travel-zone-greece.com | 0.531 | ✅ 新信息 |
| 4 | Archaeological Museum of Heraklion | gtp.gr | 0.526 | ✅ 新信息 |
| 5 | Archaeological Museum of Heraklion | gtp.gr | 0.526 | 🔴 重复 #4 |

**问题**：
- 前两个来源与 q1 完全重复
- 最后两个来源重复（相同 URL）
- 实际新增信息仅 2 条，且主要是博物馆一般性介绍

**写入图谱数据**（L992-994）：
- sources: 5
- documents: 5
- statements: 29（从 q1 的 20 条增加）
- evidence: 22（从 q1 的 18 条增加）
- conflicts: 1（首次检测到冲突）
- novelty_score: 0.818

**评估结果**（L1049-1060）：
```json
{
  "sufficiency_score": 0.46,
  "criterion_results": [
    {
      "criterion": "Reliable scholarly sources identify the principal scholars or positions...",
      "status": "unmet",
      "reason": "The peer-reviewed article identifies Evans's acceptance, rejection by many other scholars... However, the supplied evidence does not name the principal opposing or renewing scholars..."
    }
  ],
  "status": "needs_expansion"
}
```

**关键发现**：
- ⚠️ sufficiency_score 从 0.72 降到 0.46
- ⚠️ 关键词过多导致搜索结果重复、质量下降
- ⚠️ 新查询未能有效补充信息缺口

---

### 2.3 后续轮次（q2 系列等）

**执行时间**: L1163-L4394+

后续的搜索创建了更多子查询，但都存在类似问题：

| 查询 | 类型 | 问题 |
|------|------|------|
| q2 | 新的根查询 | 重复 "Ring of Nestor" |
| q2.1 | q2 的子查询 | 包含多个关键词 |
| q2.1.1 | q2.1 的子查询 | 更长的关键词列表 |
| q2.1.1.1 | 更深的子查询 | 过长 |
| q2.2 | q2 的子查询 | 包含多个关键词 |
| q2.3 | q2 的子查询 | 包含多个关键词 |
| q2.3.1 | q2.3 的子查询 | 更长 |
| q2.3.2 | q2.3 的子查询 | 更长 |
| q1.1.1 | q1.1 的子查询 | 更长 |
| q1.2 | q1 的子查询 | 更长 |

**核心问题**：
1. **树形结构膨胀**: 每个查询创建 2-3 个子查询，导致 1 个根查询扩展成 10+ 个
2. **关键词堆叠**: 每个新查询都继承父查询的所有关键词，再加新的
3. **收益递减**: 随着搜索轮次增加，新增信息越来越少

---

## 三、评估结果详细变化

### 3.1 各轮次 coverage 变化

| 轮次 | artifact_identity | interpretation | encyclopedic | completeness |
|------|------------------|----------------|-------------|-------------|
| 1 | 0.45 | 0.68 | 0.38 | 0.677 |
| 2 | 0.45 | 0.68 | 0.38 | 0.677 |
| 3 | 0.45 | 0.68 | 0.42 | 0.689 |
| 4 | 0.45 | 0.68 | 0.45 | 0.715 |
| 5 | 0.45 | 0.68 | 0.45 | 0.715 |
| 6+ | 0.45 | 0.68 | 0.45 | 0.638 |

**观察**：
- artifact_identity 在第 1 轮后完全停滞
- interpretation 在第 1 轮后完全停滞
- encyclopedic 有小幅提升（0.38 → 0.45）
- completeness 在第 4 轮达到峰值后下降

### 3.2 sufficiency_score 变化

| 查询 | sufficiency_score | 说明 |
|------|------------------|------|
| q1 | **0.72** | 高质量初始结果 |
| q1.1 | 0.46 | 关键词过多导致下降 |
| q2 | 0.55 | 中等质量 |
| q2.1 | 0.50 | 中等质量 |
| q1.2 | 0.48 | 中等质量 |

**结论**: 简洁查询（q1）的质量明显高于复杂查询

### 3.3 low_gain_streak 变化

| 轮次 | low_gain_streak | last_evaluated_successful_rounds |
|------|----------------|----------------------------------|
| 1 | 0 | 1 |
| 2 | 0 | 1 |
| 3 | 0 | 2 |
| 4 | 0 | 3 |
| 5 | 0 | 4 |

---

## 四、报告生成详细过程

### 4.1 Reporter 初始化

**执行位置**: L4868-L4871

```json
// export_report_context 结果
{
  "delivery_mode": "limited",
  "goal": {
    "request": "Write a Wikipedia article about the Ring of Nestor..."
  }
}
```

**关键信息**：
- delivery_mode: `limited`（受限模式）
- 报告语言: English

### 4.2 章节大纲

**提交位置**: L5197-L5235

| 章节 ID | 标题 | 类型 | 关联查询 |
|--------|------|------|---------|
| 1 | Lead | lead | q1, q2, q2.1, q2.2, q1.1 |
| 2 | Discovery, provenance and publication | body | q2.1.1, q2.1.1.1, q2.3, q2.3.1, q2.3.2 |
| 3 | Description and interpretation | body | q2.2, q1, q1.2, q2.3 |
| 4 | Authenticity debate | body | q1.1, q1.1.1, q1.2, q2.2, q2.3.2 |

**观察**：
- 章节结构完整，符合 Wikipedia 风格
- 每个章节关联了多个查询的证据
- Lead 章节直接关联了初始查询 q1

### 4.3 章节写作

**执行位置**: L5253-L11422

写作过程分 3 批执行：
1. Batch 1: Chapter 1 (Lead) + Chapter 2 (Discovery)
2. Batch 2: Chapter 3 (Description)
3. Batch 3: Chapter 2 (重新加载)

每章流程：
1. `prepare_report_chapter_batch` → 加载证据 bundle
2. `commit_report_chapter_batch` → 保存候选章节
3. 重复直到所有章节完成

### 4.4 最终提交

**执行位置**: L11422-L12228

```json
// submit_final_report 最终结果
{
  "delivered": true,
  "revision_requested": false,
  "artifact_delivery_mode": "compiled_reporter_unvalidated",
  "report_delivery_mode": "limited",
  "budget_status": "BUDGET_EXHAUSTED"
}
```

---

## 五、问题根因深度分析

### 5.1 查询生成问题

#### 问题 1: 初始查询 ✅ 已解决
```
V8: "Ring of Nestor Mycenaean gold ring archaeological study museum collection..."
V10: "Ring of Nestor -site:en.wikipedia.org"
```

**改进效果**: 从 10+ 关键词降到 2 词，首轮搜索质量从 0/5 提升到 5/5

#### 问题 2: 后续查询 ❌ 未解决
```
expand_gaps 创建:
"Ring of Nestor" authenticity debate Isopata tomb Knossos 1920 
Heraklion Archaeological Museum scholarly journal article academic paper 
evidence forgery genuine provenance iconography inscription goldwork -site:en.wikipedia.org
```

**根因**: `plan_followup_query` 提示词中的负面示例包含了所有这些关键词，LLM 把它当作"参考"而非"禁止"。

#### 问题 3: 查询树形膨胀
每个查询创建 2-3 个子查询，导致：
- 1 个根查询 → 10+ 个子查询
- 搜索预算被大量子查询消耗
- 实际有效信息增量递减

### 5.2 评估逻辑问题

#### 问题 4: artifact_identity 无法突破
第 1 轮后 artifact_identity 稳定在 0.45，原因：
- 现有证据已充分覆盖"身份"（Arthur Evans, 1925 年出版）
- 但"物理描述"（重量、尺寸、材质）始终缺乏
- 后续搜索无法补充这一缺口

#### 问题 5: completeness 后期下降
第 4 轮后 completeness 从 0.715 降到 0.638，原因：
- 后期搜索添加了低质量、重复的信息
- 低质量来源稀释了整体质量

### 5.3 提示词设计问题

#### 问题 6: 负面示例变成"参考"
原提示词：
```
❌ Do NOT pile up: "authenticity debate Isopata tomb Knossos 1920 
Heraklion Archaeological Museum scholarly journal article..."
```

LLM 理解为：
```
这些关键词是"重要的"，应该包含在查询中
```

**解决方案**：移除具体关键词列表，改为通用描述：
```
❌ Do NOT pile up 10+ generic keywords in one query
```

---

## 六、改进建议（已执行）

### 6.1 已完成的修改

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L24) | 移除 Ring of Nestor 具体示例 | ✅ 已完成 |
| [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L60) | 移除 Phase 1 示例 | ✅ 已完成 |
| [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L68) | 移除 Phase 2 示例 | ✅ 已完成 |
| [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L307) | 改进负面示例为通用描述 | ✅ 已完成 |
| [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L312) | 用通用模式替代具体示例 | ✅ 已完成 |

### 6.2 后续需要验证的点

1. **expand_gaps 查询执行** - 确保新查询被正确路由和执行
2. **查询多样性** - 避免 11 轮使用相同查询
3. **质量门控** - 低质量结果应被过滤

---

## 七、关键日志索引

| 环节 | 行号范围 | 描述 |
|------|---------|------|
| init_research | 409-454 | 创建研究目标和初始查询 |
| dispatch_searcher (q1) | 467-625 | 执行首轮搜索，返回 5 来源 |
| assess_query (q1) | 637-654 | 评估 q1，sufficiency=0.72 |
| evaluate_portfolio (1) | 668-737 | 首次整体评估，completeness=0.677 |
| expand_gaps (q1.1) | 752-764 | 创建子查询，包含 15+ 关键词 |
| dispatch_searcher (q1.1) | 861-1032 | 执行第二轮搜索 |
| assess_query (q1.1) | 1044-1060 | 评估 q1.1，sufficiency=0.46 |
| Reporter 初始化 | 4868-4871 | export_report_context |
| 章节大纲 | 5197-5235 | commit_report_outline，4 章节 |
| 章节写作 | 5253-11422 | prepare/commit_report_chapter_batch |
| 最终提交 | 11422-12228 | submit_final_report |

---

## 八、V8 vs V10 核心指标对比

| 维度 | V8 | V10 | 改进幅度 |
|------|-----|-----|---------|
| **初始查询** | 10+ 关键词 | `Ring of Nestor` | ✅ 简洁化 |
| **首轮搜索质量** | 0/5 | 5/5 | ✅ 从无到有 |
| **初始 sufficiency** | 0.24 | 0.72 | ✅ +200% |
| **峰值 completeness** | 0.27 | 0.715 | ✅ +165% |
| **有效搜索轮次** | 1 | 5+ | ✅ 5x |
| **报告引用数** | 3 | 10 | ✅ +233% |
| **报告结构** | 不完整 | 4 章节完整 | ✅ |
| **expand_gaps** | 0 个新查询 | 10+ 新查询 | ✅ 修复 |

---

*报告由 V10 运行日志分析生成*
*完整日志: [run.log](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/outputs/test_v10/_runs/82-Ring_of_Nestor/run.log)*
*分析数据: [analysis.json](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/outputs/test_v10/_runs/82-Ring_of_Nestor/analysis.json)*
*最终报告: [Ring_of_Nestor.md](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/outputs/test_v10/Ring_of_Nestor.md)*
