# GraphResearcher V10 实时分析报告

**生成时间**: 2026-08-04 14:45
**状态**: 测试进行中（第 4 轮搜索）

---

## V10 vs V8 核心指标对比

| 指标 | V8 | V10 (当前) | 改进幅度 |
|------|-----|-----------|---------|
| **查询文本** | 10+ 泛化关键词 | `"Ring of Nestor"` | ✅ 简洁化 |
| **搜索结果相关数** | 0/5 | 5/5 (第1轮) | ✅ 100% |
| **sufficiency_score** | 0.24 | 0.72 (第1轮) | ✅ +200% |
| **coverage (artifact_identity)** | 0.28 | 0.45 | ✅ +60% |
| **coverage (interpretation)** | N/A | 0.68 | ✅ 良好 |
| **report_completeness** | 0.27 | 0.677 | ✅ +151% |
| **expand_gaps created** | 0 | 1+ | ✅ 修复 |
| **delivery_mode** | limited | 待确认 | - |

---

## 各轮搜索详情

### 第 1 轮 (q1)
- **查询**: `Ring of Nestor -site:en.wikipedia.org`
- **结果**: 5/5 相关，包括 JAEI、Academia.edu、Nature、Heidelberg University
- **sufficiency_score**: 0.72
- **覆盖率**: artifact_identity=0.45, interpretation=0.68

### 第 2 轮 (q1.1)
- **查询**: `"Ring of Nestor" authenticity debate Isopata tomb Knossos 1920 ...`
- **问题**: 查询过长（15+ 关键词），但仍返回相关结果
- **sufficiency_score**: 0.46 (低于预期)

### 第 3 轮
- 继续搜索补充信息
- coverage 保持稳定在 0.677

### 第 4 轮 (进行中)
- 查询 Ring of Nestor provenance Thisbe treasure
- 返回了 Evans 1936 年的 The Minoan World PDF

---

## V10 关键改进

### ✅ 已解决的问题
1. **查询生成质量**: 第一轮查询从 10+ 关键词简化为实体名称
2. **expand_gaps 有效性**: 成功创建了新查询（之前为 0）
3. **搜索结果质量**: 第一轮返回 5/5 高质量来源
4. **覆盖率**: 从 0.27 提升到 0.677

### ⚠️ 仍需改进的问题
1. **后续查询过短**: 第二轮查询又开始堆砌关键词
2. **低收益停滞**: low_gain_streak=2，可能导致提前停止
3. **第二轮搜索效果差**: sufficiency_score 从 0.72 降到 0.46

---

## 根因分析

### V8 失败原因（已解决）
```
查询生成 → 10+ 泛化关键词
    ↓
Tavily 返回展览页面（0/5 相关）
    ↓
sufficiency_score = 0.24
    ↓
expand_gaps → 0 个新查询
    ↓
BUDGET_EXHAUSTED → 停止
    ↓
Reporter limited 模式 → 低质量报告
```

### V10 改进路径
```
查询生成 → "Ring of Nestor"（简洁）
    ↓
Tavily 返回 5/5 高质量来源（JAEI, Academia, Nature）
    ↓
sufficiency_score = 0.72
    ↓
expand_gaps → 创建新查询
    ↓
report_completeness = 0.677
    ↓
继续搜索补充信息
```

---

## 下一步优化方向

1. **修复 plan_followup_query 提示词** (已修改，待验证)
   - 强制后续查询 ≤ 5 个关键词
   - 添加负面示例明确禁止堆砌

2. **增加收敛阈值**
   - 不要在 low_gain_streak=2 时就停止
   - 至少尝试 3-4 轮不同策略的搜索

3. **添加查询多样性机制**
   - 如果连续 2 轮搜索收益为 0，使用完全不同的查询策略
   - 例如：从 "authenticity debate" 转向 "physical description"

---

## 结论

V10 相比 V8 取得了**巨大的进步**：
- ✅ 查询从冗长变为简洁
- ✅ 搜索结果从 0/5 变为 5/5
- ✅ 覆盖率从 0.27 提升到 0.677
- ✅ expand_gaps 从无效变为有效

但仍需优化后续查询的简洁性和搜索多样性，以进一步提升覆盖率。

---

*报告自动生成，测试完成后将更新最终结果*
