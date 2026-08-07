# V11 测试分析报告

**生成时间**: 2026-08-04 17:10:00
**测试目标**: 验证 V11 改进方案效果
**测试脚本**: test_wlc.py
**测试参数**: seed=42, sample-size=1

---

## 1. 测试概述

### 1.1 测试配置
```bash
python test_wlc.py \
  --seed 42 \
  --sample-size 1 \
  --output-path outputs/test_v11 \
  --prompt-path "ga_100.json"
```

### 1.2 改进方案
| 方案 | 描述 | 状态 |
|------|------|------|
| A | 失败检测阈值（SUFFICIENCY_FAILURE_THRESHOLD=0.1） | ✅ 已实施 |
| B | 强化 Gaps 多样性 Prompt（至少 3 个维度） | ✅ 已实施 |
| C | 代码层面强制补充 Gaps（MIN_GAPS_COUNT=3） | ✅ 已实施 |

---

## 2. 报告质量分析

### 2.1 查询维度覆盖

V11 报告包含 **4 个不同维度** 的查询章节：

| # | 查询文本 | 维度 | 关键词数 |
|---|---------|------|---------|
| 1 | `Ring of Nestor -site:en.wikipedia.org` | 实体识别 | 2 |
| 2 | `"Ring of Nestor" provenance "1924" "chain of custody" ownership museum -site:en.wikipedia.org` | provenance | 6 |
| 3 | `"Ring of Nestor" gold dimensions engraved bezel physical description museum catalog -site:en.wikipedia.org` | physical_description | 7 |
| 4 | `"Ring of Nestor" authenticity forgery "Egyptian prototypes" "butterfly motif" scholars -site:en.wikipedia.org` | authenticity_debate | 7 |

**对比 V10**：
- V10: 只有 1 个维度（authenticity），后续查询都是围绕同一维度堆砌关键词
- V11: 有 4 个不同维度，每个查询聚焦于单一维度 ✅

### 2.2 引用来源统计

| 指标 | V10 | V11 | 变化 |
|------|-----|-----|------|
| 引用来源数 | 15 | 17 | +13% |
| 高质量来源（学术/博物馆） | 8 | 10 | +25% |
| 维度覆盖数 | 1 | 4 | +300% |

### 2.3 报告内容分析

#### 章节 1：实体识别
- ✅ 正确识别 Ring of Nestor 是 Arthur Evans 1925 年的作品
- ✅ 提供了基本的背景信息
- ✅ 引用了 HathiTrust、Nature、Academia.edu 等权威来源

#### 章节 2：Provenance（来源）
- ⚠️ 搜索结果相关性低：返回了一些不相关的结果（如 Museum der bildenden Künste Leipzig、NMAI 档案等）
- ❌ 没有找到 Ring of Nestor 的完整 chain of custody
- ✅ 明确指出了信息缺失："The supplied material does not establish a documented provenance..."

#### 章节 3：Physical Description（物理描述）
- ⚠️ 搜索结果部分相关：找到了一些物理特征描述（bezel 28 × 17 mm），但不确定是否属于 Ring of Nestor
- ❌ 信息不完整："The supplied authoritative article extract does not provide the Ring of Nestor's complete dimensions..."
- ✅ 诚实报告了信息局限性

#### 章节 4：Authenticity Debate（真实性争议）
- ✅ 返回了高质量的学术研究
- ✅ 涵盖了多个学术观点：支持真实性、质疑真实性、重新评估等
- ✅ 引用了多个权威学术来源
- ✅ 是报告中质量最高的章节

---

## 3. 关键改进点

### 3.1 ✅ 成功改进

#### 改进 1：查询维度多样性
- **效果**: 从 1 个维度增加到 4 个维度
- **原因**: 方案 B（Prompt 强化）+ 方案 C（代码补充）共同作用
- **验证**: 报告中有 4 个不同主题的查询章节

#### 改进 2：查询聚焦单一维度
- **效果**: 每个查询聚焦于一个具体维度
- **对比**: V10 的 q1.1 包含 20+ 关键词，覆盖 5+ 维度；V11 的 q2 只有 6 关键词，聚焦 provenance
- **验证**: 查询文本分析显示每个查询都有明确的维度关键词

#### 改进 3：失败检测机制
- **效果**: 状态转换规则支持 `assessing -> failed`
- **修复**: 更新了 `_QUERY_TRANSITIONS` 字典
- **验证**: 没有出现状态转换错误

### 3.2 ⚠️ 部分改进

#### 改进 4：Gaps 自动补充
- **问题**: 搜索日志显示 `gaps created: 1`，说明自动补充可能没有完全生效
- **可能原因**: 
  1. LLM 创建的 gap 已经通过了某种验证，没有触发补充逻辑
  2. 补充逻辑的触发条件可能需要调整
- **建议**: 检查 `created_gaps` 的实际内容和补充逻辑的执行路径

#### 改进 5：搜索结果质量
- **问题**: 某些维度（如 provenance）的搜索结果相关性仍然较低
- **表现**: 
  - provenance 查询返回了不相关的博物馆档案
  - physical_description 查询的结果不够明确
- **建议**: 
  1. 优化查询关键词选择，避免使用过于泛化的词
  2. 考虑添加更多唯一标识符（如具体的博物馆名称、目录号等）

---

## 4. 问题分析

### 4.1 Provenance 查询结果相关性低

**查询文本**: `"Ring of Nestor" provenance "1924" "chain of custody" ownership museum`

**问题**:
- `"museum"` 关键词过于泛化，返回了各种博物馆的档案
- `"chain of custody"` 是法律术语，不适用于考古文物
- `"1924"` 可能匹配到其他 1924 年的藏品

**建议修改**:
```python
# 更精准的查询
"Ring of Nestor" provenance ownership Ashmolean Museum Thisbe
```

### 4.2 Physical Description 信息不完整

**查询文本**: `"Ring of Nestor" gold dimensions engraved bezel physical description museum catalog`

**问题**:
- `"museum catalog"` 返回了博物馆目录，但不是 Ring of Nestor 的目录
- 搜索结果中有 bezel 尺寸，但不确定是否属于 Ring of Nestor

**建议修改**:
```python
# 更精准的查询
"Ring of Nestor" gold signet ring bezel dimensions 28x17
```

---

## 5. V10 vs V11 对比

| 指标 | V10 | V11 | 改进 |
|------|-----|-----|------|
| 查询维度数 | 1 | 4 | ✅ +300% |
| 引用来源数 | 15 | 17 | ✅ +13% |
| 查询聚焦度 | 低（20+ 关键词） | 高（6-7 关键词） | ✅ |
| 失败检测 | 不支持 | 支持 | ✅ |
| 状态转换错误 | 无 | 修复 | ✅ |
| 报告完整性 | 中 | 中（部分维度信息不足） | ⚠️ |
| 搜索结果相关性 | 中 | 参差不齐 | ⚠️ |

---

## 6. 后续优化建议

### 6.1 高优先级

#### 优化 1：Provenance 查询关键词
- **问题**: 当前 provenance 查询返回不相关结果
- **建议**: 
  - 移除 `"chain of custody"`（法律术语）
  - 添加具体的收藏机构名（如 Ashmolean Museum）
  - 添加发现地点（如 Thisbe, Boeotia）

#### 优化 2：触发 Gaps 补充的条件
- **问题**: 日志显示 `gaps created: 1`，但实际报告中有 4 个维度
- **需要调查**: 
  - 是 LLM 创建了多个 gaps，还是自动补充生效了
  - `created_gaps` 计数是否准确

### 6.2 中优先级

#### 优化 3：搜索结果质量评估
- **问题**: 某些维度的搜索结果相关性仍然较低
- **建议**: 
  - 添加搜索结果的相关性评分
  - 当搜索结果不相关时，自动调整查询策略

#### 优化 4：查询生成策略
- **问题**: 查询关键词选择不够精准
- **建议**: 
  - 从已有的高质量来源中提取关键词
  - 使用更具体的标识符（如人名、机构名、具体年份）

### 6.3 低优先级

#### 优化 5：报告写作质量
- **问题**: 报告直接复制了搜索结果，没有进行有效的综合分析
- **建议**: 
  - 改进 Reporter 的写作 prompt
  - 添加信息综合和整合的指导

---

## 7. 关键代码修改

### 7.1 新增常量
```python
# 文件: src/agents/memory_manager.py
SUFFICIENCY_FAILURE_THRESHOLD = 0.1  # 失败检测阈值
MIN_GAPS_COUNT = 3  # 最少 Gaps 数量
MAX_CHILD_QUERIES = 3  # 最大子查询数
MAX_QUERY_DEPTH = 4  # 最大查询深度
```

### 7.2 新增失败检测逻辑
```python
# 文件: src/agents/memory_manager.py (assess_query 方法)
# 三个失败检测条件：
# 1. sufficiency_score < 0.1 且有 gaps
# 2. 查询深度 >= MAX_QUERY_DEPTH
# 3. 活跃子查询数 >= MAX_CHILD_QUERIES
```

### 7.3 新增 Gaps 自动补充
```python
# 文件: src/agents/memory_manager.py (assess_query 方法)
# 当 created_gaps 数量 < MIN_GAPS_COUNT 时，
# 从 7 个预定义维度模板中补充缺失的维度
```

### 7.4 更新状态转换规则
```python
# 文件: src/tools/graph_tools.py
_QUERY_TRANSITIONS = {
    "assessing": {"sufficient", "needs_expansion", "blocked", "failed"},  # 添加 failed
    "needs_expansion": {"waiting_children", "sufficient", "blocked", "failed"},  # 添加 failed
    "waiting_children": {"assessing", "failed"},  # 添加 failed
}
```

---

## 8. 输出文件清单

```
outputs/test_v11/
├── Ring_of_Nestor.md                    # 最终报告
├── V11_improvement_summary.md           # 改进方案总结
└── V11_test_analysis_report.md          # 本报告

outputs/search_test/
├── search_results.md                    # 搜索质量测试报告
└── raw_results.json                    # 原始搜索结果
```

---

## 9. 结论

V11 改进方案取得了**部分成功**：

### ✅ 成功的改进
1. **查询维度多样性**: 从 1 个维度增加到 4 个维度
2. **查询聚焦度**: 每个查询聚焦于单一维度，关键词数量控制在 6-7 个
3. **失败检测机制**: 支持将查询标记为 `failed`
4. **状态转换规则**: 修复了 `assessing -> failed` 的转换错误

### ⚠️ 需要继续优化
1. **搜索结果相关性**: 某些维度（如 provenance）的搜索结果仍然不相关
2. **Gaps 自动补充**: 需要验证补充逻辑是否完全生效
3. **报告内容质量**: 报告需要更好地综合分析信息

### 下一步建议
1. 优化 provenance 和 physical_description 的查询关键词
2. 检查 Gaps 自动补充的执行路径
3. 考虑添加搜索结果的相关性反馈机制

---

*报告由 V11 测试分析自动生成*
*分析日期: 2026-08-04*
