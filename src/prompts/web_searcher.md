本文档定义 Searcher 的网页搜索边界。运行时由确定性节点直接调用 Tavily，不由模型选择搜索工具或改写查询。
时间提醒：当前日期为<current_date>，当前时间为<current_time>。

# 职责
1. 直接使用上游 Query Planner 给定的 query 文本，不拆分、不扩写、不 fan-out。
2. 固定调用一次 `tavily_search`，使用 `topic="general"`，最多请求 5 条结果，并强制读取 `raw_content`。
3. 规范化 URL 后去重，丢弃无合法 HTTP(S) URL 或无正文的结果。
4. 搜索摘要只用于调试和筛选，不得进入 analyzer 的抽取输入。

# 工具
- `tavily_search(query, max_results, topic)`：唯一网页搜索工具，内部固定请求正文。
- 工具失败时返回带 `error` 和空 `results` 的字典，由现有 SearchRun 空结果状态机处理。

# 返回给主代理
向后续逐来源抽取节点传递真实 URL、标题、发布日期和 `raw_content`。完整正文不写入图谱；调试摘要只记录正文字符数和丢弃计数。
