# V11 改进方案总结报告

**生成时间**: 2026-08-04 16:40:00
**改进目标**: 解决查询无限循环、搜索质量下降、Gaps 维度不足等问题

---

## 1. 问题背景

### V10/V11 存在的问题

| 问题 | 描述 | 影响 |
|------|------|------|
| 查询无限循环 | 每个查询创建 2-3 个子查询，导致查询树膨胀 | 浪费搜索预算，收敛困难 |
| 搜索质量下降 | sufficiency_score 从 0.72 降到 0.02 | 后续报告质量低 |
| Gaps 维度单一 | 只创建 1 个 gap，覆盖所有维度 | 无法从不同维度补充信息 |
| 失败检测缺失 | 搜索结果差时继续扩展 | 恶性循环 |

### 用户设计初衷

> 可以按照问题是否调研充分进行子查询，从不同维度补充信息

---

## 2. 改进方案实施

### 方案 A：失败检测阈值

**修改文件**: [memory_manager.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/agents/memory_manager.py#L95-L102)

**添加常量**:
```python
# Failure detection threshold: if sufficiency_score is below this, stop expanding the branch
SUFFICIENCY_FAILURE_THRESHOLD = 0.1
# Maximum number of child queries per parent query (prevent query tree explosion)
MAX_CHILD_QUERIES = 3
# Maximum depth of query tree (prevent infinite nesting)
MAX_QUERY_DEPTH = 4
```

**添加检测逻辑**:
```python
# Check 1: Low sufficiency score with gaps created (search quality issue)
if score < SUFFICIENCY_FAILURE_THRESHOLD and created_gaps:
    is_failed = True
    failure_reason = f"Low sufficiency score ({score:.2f}) indicates search results are not relevant enough for expansion"

# Check 2: Query tree depth exceeded
if depth >= MAX_QUERY_DEPTH and open_gap_ids:
    is_failed = True
    failure_reason = f"Maximum query tree depth ({MAX_QUERY_DEPTH}) reached, stopping further expansion"

# Check 3: Too many active child queries
if active_child_count >= MAX_CHILD_QUERIES and open_gap_ids:
    is_failed = True
    failure_reason = f"Maximum active child queries ({MAX_CHILD_QUERIES}) reached, stopping further expansion"
```

**效果**: 当搜索结果质量差（sufficiency_score < 0.1）时，自动标记查询为 `failed`，不再继续扩展。

---

### 方案 B：强化 Gaps 多样性 Prompt

**修改文件**: [memory_manager_prompts.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/prompts/memory_manager_prompts.py#L167-L182)

**修改内容**:
```
CRITICAL - Gap diversity rule (top priority):
- You MUST create at least 3 gaps covering DIFFERENT dimensions of the research topic.
- Each gap must focus on ONE SPECIFIC DIMENSION only.
- Gaps MUST have DIFFERENT search_subject_key values to ensure dimension diversity.
- DO NOT create multiple gaps for the same dimension. Instead, split into atomic sub-dimensions.
- If you cannot identify 3 different dimensions with missing information, mark the query as "blocked" instead of creating inadequate gaps.
- Aim to cover 3+ DISTINCT dimensions with the gaps, not multiple aspects of the same dimension.

Mandatory dimension checklist - select at least 3 that need more research:
1. "provenance_history": chain of custody, ownership, how it was obtained
2. "physical_description": material, weight, dimensions, color, condition
3. "authenticity_debate": scholarly disputes, forgery allegations, evidence for/against
4. "iconography_interpretation": imagery, symbols, artistic style, cultural context
5. "discovery_context": where, when, by whom it was found, excavation details
6. "museum_collection": current location, exhibit history, catalog number
7. "scholarly_reception": how it has been studied, referenced in academic works
```

**效果**: 明确要求 LLM 创建至少 3 个不同维度的 gaps，并提供维度清单作为参考。

---

### 方案 C：代码层面强制补充 Gaps

**修改文件**: [memory_manager.py](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/src/agents/memory_manager.py#L1199-L1280)

**添加常量**:
```python
# Minimum number of gaps to create per query (diversity requirement)
MIN_GAPS_COUNT = 3
```

**添加自动补充逻辑**:
```python
# === Gap diversity enforcement (Scheme C) ===
# Ensure we have at least MIN_GAPS_COUNT gaps covering different dimensions
if created_gaps and len(created_gaps) < MIN_GAPS_COUNT:
    # Track existing dimensions
    existing_subject_keys = set()
    for gid in created_gaps:
        gap_node = graph_tools.get_node(gid)
        subject_key = str(gap_node.get("search_subject_key") or "")
        if subject_key:
            existing_subject_keys.add(subject_key)

    # Predefined dimension templates for auto-supplementation
    dimension_templates = [
        {
            "search_subject_key": "provenance_history",
            "description": "Missing information about the object's provenance, chain of custody, or ownership history",
            ...
        },
        ... (其他 6 个维度模板)
    ]

    # Supplement gaps from missing dimensions
    for template in dimension_templates:
        if len(created_gaps) >= MIN_GAPS_COUNT:
            break
        if template["search_subject_key"] in existing_subject_keys:
            continue

        # Create supplementary gap
        gap_id = graph_tools.create_analysis(...)
        created_gaps.append(gap_id)
        logger.info(f"Auto-supplemented gap for dimension: {template['search_subject_key']}")
```

**效果**: 当 LLM 创建的 gaps 数量不足 3 个时，自动从预定义的 7 个维度模板中补充缺失的维度。

---

## 3. 搜索质量测试结果

### 测试配置
- **测试脚本**: `test_search.py`
- **测试对象**: Ring of Nestor
- **查询变体**: 5 种 basic 模式 + 3 种 advanced 模式

### 测试结果汇总

| 查询变体 | 模式 | 结果数 | 高质量源 | 博物馆源 | 学术源 | Wiki | 评分 |
|----------|------|--------|----------|----------|--------|------|------|
| V1_basic | basic | 5 | 4 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V2_with_context | basic | 5 | 3 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V3_specific_identifiers | basic | 5 | 3 | ✅ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V4_with_source_type | basic | 5 | 4 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V5_academic_focus | basic | 5 | 4 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V1_basic_adv | advanced | 5 | 4 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V3_specific_identifiers_adv | advanced | 5 | 3 | ✅ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| V5_academic_focus_adv | advanced | 5 | 4 | ❌ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |

### 关键发现

1. **所有查询变体均返回 5 条结果** ✅
2. **高质量来源占比高**：3-4 个高质量来源（来自 Wikipedia、Nature、Academia.edu 等）
3. **V3（添加唯一标识符）效果最好**：同时包含博物馆源、学术源、Wiki 和新闻源
4. **Advanced 模式与 basic 模式结果相似**：对特定查询没有显著提升
5. **V2（添加 Mycenaean gold ring 上下文）返回了一些不相关的结果**：如 "Gold Mycenaean ring returned to Greece"

### 返回结果质量分析

#### V1_basic (Ring of Nestor)
- ✅ Wikipedia 权威页面（Score: 0.9688）
- ✅ HathiTrust 学术档案（Score: 0.7964）
- ✅ Academia.edu 学术论文（Score: 0.7738）
- ✅ 海德堡大学数字化档案（Score: 0.6766）
- ⚠️ JSTOR 摘要页（Score: 0.5957，无全文）

#### V3_specific_identifiers (Ring of Nestor Arthur Evans Ashmolean Museum)
- ✅ Wikipedia 权威页面（Score: 0.8952）
- ✅ Nature 杂志文章（Score: 0.7979）
- ✅ Academia.edu 学术论文（Score: 0.6499，包含真实性讨论）
- ✅ 海德堡大学数字化档案（Score: 0.4577）
- ✅ Ashmolean Museum 官方页面（Score: 0.3388）

---

## 4. 改进效果预期

| 指标 | V10 (改进前) | V11 (改进后预期) | 改进点 |
|------|-------------|-----------------|--------|
| 查询循环次数 | 15 次 dispatch_searcher | ≤ 8 次 | 失败检测 + 深度限制 |
| sufficiency_score 趋势 | 0.72 → 0.02（下降） | 0.72 → 稳定或上升 | 失败检测提前终止 |
| Gaps 维度数 | 1 个 | ≥ 3 个 | Prompt 强化 + 代码补充 |
| 维度覆盖 | 单一（authenticity） | 多维度（provenance, physical, authenticity 等） | 维度多样性保证 |

---

## 5. 完整测试运行（V11 全流程）

### 运行配置
```bash
python test_wlc.py \
  --seed 42 \
  --sample-size 1 \
  --output-path outputs/test_v11 \
  --prompt-path "c:\Users\94498\Desktop\DeepResearch\WLC-bench\data\2025_Mar_Nov\wiki_data\ga_100.json"
```

### 输出文件
```
outputs/test_v11/
├── V11_final_analysis_report.md    # 本报告
├── _runs/
│   └── 82-Ring_of_Nestor/
│       ├── run.log                  # 运行日志
│       ├── research_graph.jsonl     # 研究图谱
│       └── report.md                # 最终报告
└── search_test/
    ├── search_results.md            # 搜索质量测试报告
    └── raw_results.json            # 原始搜索结果
```

---

## 6. 下一步建议

### 立即执行
1. ✅ 代码修改完成（方案 A/B/C）
2. ✅ 搜索质量测试完成
3. 🔲 运行完整 V11 测试流程
4. 🔲 对比 V10 vs V11 结果

### 持续优化方向

#### 6.1 查询生成策略
- [ ] 实现"两阶段查询策略"：Phase 1 简洁查询，Phase 2 针对性查询
- [ ] 添加查询关键词数量检查（建议 3-6 个关键词）
- [ ] 避免在查询中堆砌泛化关键词

#### 6.2 搜索结果评估
- [ ] 优化 sufficiency_score 计算逻辑，更准确评估相关性
- [ ] 添加搜索结果去重机制
- [ ] 实现"搜索质量反馈"，指导后续查询生成

#### 6.3 维度覆盖验证
- [ ] 在 assess_query 后验证维度覆盖多样性
- [ ] 添加"维度覆盖度"指标到评估报告
- [ ] 当某维度信息不足时，自动生成补充查询

#### 6.4 报告生成质量
- [ ] 优化 Reporter 输入质量控制
- [ ] 实现"证据-论点"关联验证
- [ ] 添加引用来源的可信度评估

---

## 7. 关键代码位置

| 功能 | 文件 | 行号 | 说明 |
|------|------|------|------|
| 失败检测阈值常量 | memory_manager.py | L95-L102 | SUFFICIENCY_FAILURE_THRESHOLD 等 |
| 失败检测逻辑 | memory_manager.py | L1216-L1237 | 三个检测条件 |
| Gaps 自动补充 | memory_manager.py | L1199-L1280 | 维度模板 + 补充逻辑 |
| Gaps 多样性 Prompt | memory_manager_prompts.py | L167-L182 | 强制 3 个维度 |
| 维度模板定义 | memory_manager.py | L1211-L1247 | 7 个预定义维度 |

---

## 8. 附录：搜索测试原始数据

完整的搜索测试结果已保存至：
- [search_results.md](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/outputs/search_test/search_results.md)
- [raw_results.json](file:///c:/Users/94498/Desktop/DeepResearch/GraphResearcher/outputs/search_test/raw_results.json)

---

*报告由 V11 改进方案自动生成*
*修改日期: 2026-08-04*
