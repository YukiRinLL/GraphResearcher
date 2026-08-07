# V7/V8/V9 搜索环节问题分析报告

**生成时间**: 2026-08-04
**分析目标**: 定位搜索后、Reporter 前的处理环节问题

---

## 一、核心发现：查询生成是根因

### GraphResearcher 实际生成的查询 vs 测试查询效果对比

| 来源 | 查询文本 | 相关结果数 | 最佳来源 |
|------|---------|-----------|---------|
| **V7** | `"Ring of Nestor" Pylos Messenia artifact authenticity provenance scholarly archaeology Bronze Age` | 2/5 | Academia.edu (0.624) |
| **V8** | `Ring of Nestor Mycenaean gold ring archaeological study museum collection scholarly publication provenance iconography dating` | **0/5** | UC Cincinnati (0.571) ❌ |
| **V9** | `Ring of Nestor Nestor archaeological artifact scholarly publication museum collection 2025` | **0/5** | Pylos Exhibition (0.650) ❌ |
| **测试 V1** | `Ring of Nestor` | **5/5** | HathiTrust (0.796) ✅ |
| **测试 V3** | `Ring of Nestor gold signet ring Arthur Evans 1925` | **5/5** | Nature (0.825) ✅ |

**结论**: GraphResearcher 生成的查询过于冗长（10+ 泛化关键词），导致 Tavily 返回展览页面而非学术资料。

---

## 二、V8 详细流程分析（搜索后 → Reporter 前）

### 步骤 1: 搜索执行
```
查询: "Ring of Nestor Mycenaean gold ring archaeological study museum 
       collection scholarly publication provenance iconography dating 
       -site:en.wikipedia.org"
```

**返回结果（全部无关）**:
1. ❌ "Nestor - Home" (UC Cincinnati) - 考古学论文列表，score: 0.571
2. ❌ "Pylos of Nestor" (国家考古博物馆) - 2026年展览页面，score: 0.482
3. ❌ "The Lord of the Gold Rings" (Academia.edu) - 仅参考文献列表，score: 0.371
4. ❌ Instagram 帖子 - 展览宣传，score: 0.340
5. ❌ "Kingdom of Pylos" (Getty Villa) - 展览预览，score: 0.280

### 步骤 2: assess_query（查询评估）
```json
{
  "sufficiency_score": 0.24,  // 极低！
  "status": "needs_expansion",
  "criterion_results": [{
    "status": "unmet",
    "reason": "no source identifies any of them as the Ring of Nestor"
  }],
  "created_gaps": ["gap_1", "gap_2", "gap_3"]  // 识别了 3 个信息缺口
}
```

**✅ 评估正确**: 系统正确识别到搜索结果不包含 Ring of Nestor 相关信息。

### 步骤 3: evaluate_research_portfolio（组合评估）
```json
{
  "objectives": [
    {
      "objective_key": "iconography-interpretation",
      "coverage": 0.18,  // 极低
      "confidence": 0.55,
      "assessment_reason": "evidence supports limited description but no attributed interpretations"
    },
    {
      "objective_key": "object-identity-context", 
      "coverage": 0.28,  // 低
      "confidence": 0.58,
      "assessment_reason": "evidence does not establish that either source concerns the Ring of Nestor"
    },
    {
      "objective_key": "article-coverage",
      "coverage": 0.14,  // 极低
      "confidence": 0.50,
      "assessment_reason": "does not cover the Ring of Nestor's identity, provenance, physical description"
    }
  ],
  "report_completeness_score": 0.269  // 总完整度仅 27%
}
```

**✅ 评估正确**: 系统正确识别到证据与 Ring of Nestor 无关。

### 步骤 4: expand_gaps（缺口扩展）❌ 关键问题！
```json
{
  "parent_id": "q1",
  "parent_status": "blocked",
  "created": [],  // ❌ 没有创建任何新查询！
  "deferred_gap_ids": ["gap_1", "gap_2", "gap_3"],
  "next_action": "get_next_actions"
}
```

**❌ 问题 1**: `expand_gaps` 识别了 3 个信息缺口，但**没有创建任何新查询**来填补这些缺口。
缺口被标记为 `deferred`（延迟），但没有后续行动。

### 步骤 5: 第二次 evaluate_research_portfolio
```json
{
  "selected_gap_ids": [],  // ❌ 没有选择任何缺口进行处理
  "last_max_marginal_utility": 0.0,  // ❌ 边际效用为 0
  "report_completeness_score": 0.269  // 与之前相同，没有改善
}
```

**❌ 问题 2**: 第二次评估时，系统没有选择任何缺口，边际效用为 0，意味着系统认为无法通过进一步搜索来改善。

### 步骤 6: assess_convergence（收敛评估）❌ 过早停止
```json
{
  "converged": true,
  "recommendation": "stop",
  "research_state": "BUDGET_EXHAUSTED",  // ❌ 预算耗尽
  "next_actions": []
}
```

**❌ 问题 3**: 虽然覆盖率仅 27%，但系统因为 `BUDGET_EXHAUSTED` 强制停止。
这是因为 `max_search_rounds: 1`，只有一轮搜索机会。

### 步骤 7: Reporter 交付
```json
{
  "report_delivery_mode": "limited",  // ❌ 受限模式
  "artifact_delivery_mode": "compiled_reporter_validated",
  "delivered": true
}
```

Reporter 被迫在 `limited` 模式下工作，只能基于 27% 的覆盖率生成报告。

---

## 三、V7 vs V8 vs V9 对比

| 指标 | V7 | V8 | V9 |
|------|-----|-----|-----|
| 查询长度 | 10 关键词 | 11 关键词 | 7 关键词 |
| 搜索轮次 | 1 | 1 | 1 |
| 搜索结果相关数 | 2/5 | 0/5 | 0/5 |
| 最佳来源 | Academia.edu (0.624) | UC Cincinnati (0.571) | Pylos Exhibition (0.650) |
| 覆盖率 (identity) | N/A | 0.28 | 0.12 |
| sufficiency_score | N/A | 0.24 | N/A |
| delivery_mode | N/A | limited | limited |

**V7 表现最好的原因**: 查询包含 `"Ring of Nestor"`（带引号的精确匹配）和更具体的术语（Pylos, Messenia, authenticity），Tavily 能更好地定位学术来源。

---

## 四、问题根因链

```
查询生成过于冗长（10+ 泛化关键词）
    ↓
Tavily 返回展览页面而非学术资料
    ↓
assess_query 评估 sufficiency_score = 0.24（正确识别问题）
    ↓
expand_gaps 识别 3 个缺口但未创建新查询 ❌
    ↓
evaluate_research_portfolio 边际效用 = 0（认为无法改善）❌
    ↓
assess_convergence 因 BUDGET_EXHAUSTED 强制停止 ❌
    ↓
Reporter 在 limited 模式下生成低质量报告
    ↓
Writing 评估: 0 胜 39 负
```

---

## 五、具体问题清单

### 问题 1: 查询生成——关键词堆砌 ❌（根因）
- **现象**: 生成的查询包含 10+ 泛化关键词
- **影响**: Tavily 搜索被稀释，返回无关结果
- **证据**: 简单查询 "Ring of Nestor" 返回 5/5 相关结果，而 V8 查询返回 0/5

### 问题 2: expand_gaps 未生成新查询 ❌
- **现象**: 识别了 3 个信息缺口但 `"created": []`
- **影响**: 无法通过新查询弥补信息缺口
- **原因**: 可能是 `max_search_rounds: 1` 导致系统认为无法再搜索

### 问题 3: max_search_rounds = 1 ❌
- **现象**: 只允许一轮搜索
- **影响**: 一次失败的搜索无法挽回
- **位置**: [test_wlc.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/test_wlc.py) 中的 `MAX_ROUNDS = 1`

### 问题 4: assess_convergence 过早停止 ❌
- **现象**: 覆盖率仅 27% 就声明 `converged: true`
- **影响**: Reporter 被迫在信息严重不足的情况下工作
- **原因**: `BUDGET_EXHAUSTED` 状态强制停止

### 问题 5: 搜索结果处理——无实体消歧 ❌
- **现象**: 搜索返回的 Pylos 展览页面被当作有效证据
- **影响**: 评估器正确识别了无关性，但无法获得更好的来源
- **对比**: V7 的 Academia.edu 论文是相关的，但 V8/V9 完全没有相关来源

---

## 六、验证数据

### 排除 Wikipedia 后的搜索测试（模拟 GraphResearcher 环境）

| 查询 | 相关结果 | 最佳来源 | Score |
|------|---------|---------|-------|
| `Ring of Nestor -site:en.wikipedia.org` | **5/5** ✅ | HathiTrust | 0.796 |
| `Ring of Nestor Arthur Evans Ashmolean Museum -site:en.wikipedia.org` | 3/5 | Nature | 0.798 |
| `Ring of Nestor gold signet ring Arthur Evans 1925 -site:en.wikipedia.org` | **5/5** ✅ | Nature | 0.825 |
| V8 风格（10+ 关键词） | 2/5 ❌ | Academia | 0.683 |
| V7 风格（带引号+具体词） | 2/5 | Academia | 0.624 |

**关键发现**: 即使排除 Wikipedia，简单查询仍能返回高质量学术来源（Nature、HathiTrust、Academia.edu、JAEI、Heidelberg University）。

---

## 七、改进建议

### 优先级 1: 修复查询生成（根因）
- 第一轮查询应**只用实体名称**：`Ring of Nestor`
- 后续查询添加从结果中发现的标识符：`Ring of Nestor Arthur Evans 1925`
- **禁止堆砌泛化关键词**（如 archaeological, study, museum collection, scholarly publication）

### 优先级 2: 增加 max_search_rounds
- 从 1 轮增加到至少 3-5 轮
- 允许第一轮失败后使用不同查询重试

### 优先级 3: 修复 expand_gaps
- 确保 expand_gaps 在识别缺口后**创建新查询**
- 新查询应基于缺口描述生成，而非重复之前的查询

### 优先级 4: 优化 assess_convergence
- 不应在覆盖率 < 50% 时声明收敛
- 应该在 BUDGET_EXHAUSTED 时尝试至少一次不同查询的重试

---

*报告基于 V7/V8/V9 运行日志和搜索测试数据生成*
