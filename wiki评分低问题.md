1.我们构造图谱的时候基于搜索结果做了很多归纳总结，生成了各种statement/analysis/claim，这些东西混在一起递给reporter。

导致影响：

A. 其中有些论断不一定是对的，影响了最后输出质量。

B. 权重分配失衡，一些无关紧要的内容被大篇幅陈述。

C. 很多被归纳过的失真的信息被放进去，导致结果里面很多“some scholars、an alternative view”这种模糊的描述，还有“subtle hand gestures”这种主观的措辞

2.搜索的时候搜索到了很多关联性不大的信息，这个我们是不是要在评判规则里面调整一下？

你帮我分析一下我说的是否正确？

我完成了图谱分析。你的两个怀疑 完全正确 ！让我用具体证据说明问题所在：

## 🔍 图谱深度分析结果
### 一、假设1验证：图谱信息混合问题（✅ 你是对的） 问题A：信息失真的三个层面
我在 research_graph.jsonl 中发现了严重的信息失真：

1. 语言转换失真

例如：博物馆原文 "subtle hand gestures" → 中文摘要 "亲密姿态不易辨认" → Claim 中变成 "subtle gestures... not easily visible to the naked eye"

- 语义在两次转换中被弱化
- 限定条件（"需要仔细观察"）被省略
2. 事实混淆 - 最严重的问题！

图谱中混合了 三个完全不同的文物 ：

文物 图谱中的描述 正确吗？ 真正的 Ring of Nestor Ashmolean Museum, 31.76g, 四象限设计 ❌ 几乎无信息 Tiryns Ring (P 6209) National Archaeological Museum, 1.9cm hoop, 两对情侣 ❌ 被错误地当作 Ring of Nestor Griffin Warrior Tomb rings Pylos, 2015年发现, 4枚金戒指 ❌ 无关内容

3. 置信度误导

- Claim ring-nestor-provenance-museum 置信度 0.97，但描述的是 错误的文物 ！
- Reporter 看到的高置信度 Claim 大部分是关于 Tiryns Ring 的 问题B：权重分配失衡
图谱中有：

- 15+ 条 Claim 描述 Tiryns Ring（错误文物）
- 0 条有效 Claim 描述真正的 Ring of Nestor
- Reporter 基于这些 Claim 写作，自然会生成错误内容 问题C：模糊表述的来源
- ring-nestor-left-couple-gestures ："subtle gestures" 直接来自博物馆展签的主观描述
- ring-nestor-myth-theseus-ariadne ："some scholars" 来自博物馆文本的归因方式
- 这些在多次转换中被保留，最终出现在报告中
### 二、假设2验证：搜索结果相关性问题（✅ 你也是对的） 搜索结果质量
Tavily 返回的 5 个来源：

# 来源 类型 相关性 问题 1 academia.edu (Eliopoulos 2013) 论文 中等 摘要信息，正文不可见 2 Cambridge JHS (Thisbê Treasure) 论文 ❌ 低 讲的是另一个文物 3 Smithsonian (Griffin Warrior) 新闻 ❌ 低 完全不相关 4 Instagram 社交媒体 ❌ 无效 只有图片，无文字 5 namuseum.gr (Tiryns Ring) 博物馆 ❌ 错误 混淆了不同文物

只有 1/5 的来源与 Ring of Nestor 真正相关！
 根本原因
测试约束禁止使用 Wikipedia（ -site:en.wikipedia.org ），但：

- Wikipedia 包含关于 Ring of Nestor 的最准确、最完整信息
- 二级来源（博物馆、新闻、预印本）的准确性参差不齐
- 搜索结果中存在严重的 实体混淆 问题
## 📋 改进计划
基于以上分析，我建议分两个层面改进：

### 第一层面：Prompt 改进（立即可做）
改进项 目标文件 具体内容 1. 来源筛选规则 searcher.md 添加明确的来源质量过滤要求，排除社交媒体、低质量新闻 2. 主题验证步骤 searcher.md 要求搜索结果必须与 User Request 中的特征（发现地点、收藏机构等）匹配 3. 保真度要求 analyzer.md 要求 Document 摘要保留原文的限定条件，明确区分 AI 推断和原文陈述 4. 信息验证要求 reporter.md 要求 Reporter 优先使用 peer-reviewed 学术来源，验证关键事实的一致性

### 第二层面：代码改进（需要更多时间）
改进项 目标代码 具体内容 1. 来源可信度评分 图谱构建逻辑 为不同类型的来源分配权重（论文>博物馆>新闻>社交） 2. Claim 一致性检查 Claim 归一化逻辑 检查多个 Statement 是否描述同一实体，如发现矛盾则标记