import asyncio
import os
from pathlib import Path
from typing import Any, Optional

try:
    import nest_asyncio
    nest_asyncio.apply()
    HAS_NEST_ASYNCIO = True
except ImportError:
    HAS_NEST_ASYNCIO = False

from memory.graph import NodeType, EdgeType, GraphNode, GraphEdge


FILE_MARKER = {"type": "_graphresearcher", "source": "graph-researcher"}


def get_default_graph_cache_dir() -> Path:
    """
    获取默认的图谱缓存目录
    
    默认情况下，图谱数据会存储在用户主目录下的 `.graphresearcher` 文件夹中。
    如果设置了环境变量 `REPO_BASE_DIR`，则会存储在该目录下。
    
    Returns:
        Path: 默认缓存目录的路径
    """
    if os.environ.get("REPO_BASE_DIR"):
        return Path(os.environ["REPO_BASE_DIR"]) / ".graphresearcher"
    return Path.home() / ".graphresearcher"


def get_graph_file_path(cache_dir: Path, context: Optional[str] = None) -> Path:
    """
    获取图谱文件的路径
    
    根据上下文名称生成图谱文件名。如果没有提供上下文名称，使用默认文件名。
    
    Args:
        cache_dir: 缓存目录路径
        context: 上下文名称（可选），用于区分不同的图谱实例
    
    Returns:
        Path: 图谱文件的完整路径
    """
    filename = "research_graph.jsonl" if context is None else f"research_graph-{context}.jsonl"
    return cache_dir / filename


def _run_async(coro):
    """
    同步运行异步函数的内部辅助函数
    
    处理不同的异步运行时场景：
    1. 如果当前没有运行中的事件循环，直接使用 asyncio.run()
    2. 如果安装了 nest_asyncio，使用 asyncio.run()
    3. 否则使用线程池执行异步函数
    
    Args:
        coro: 异步协程对象
    
    Returns:
        协程执行结果
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if HAS_NEST_ASYNCIO:
        return asyncio.run(coro)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


_manager_cache = {}


def _get_manager(cache_dir: Optional[str] = None):
    """
    获取或创建 GraphManager 实例（内部缓存）
    
    使用单例模式管理 GraphManager 实例，避免重复创建。
    
    Args:
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        GraphManager: 图谱管理器实例
    """
    from memory.graph import GraphManager
    cache_key = cache_dir if cache_dir else "default"
    if cache_key not in _manager_cache:
        _manager_cache[cache_key] = GraphManager(cache_dir=cache_dir)
    return _manager_cache[cache_key]


def clear_manager_cache(cache_dir: Optional[str] = None):
    """
    清除 GraphManager 缓存
    
    如果指定了缓存目录，则只清除该目录对应的管理器；否则清除所有缓存。
    
    Args:
        cache_dir: 缓存目录路径（可选）
    """
    if cache_dir:
        cache_key = cache_dir if cache_dir else "default"
        if cache_key in _manager_cache:
            del _manager_cache[cache_key]
    else:
        _manager_cache.clear()


def add_node(
    node_type: str,
    attributes: dict[str, Any],
    node_id: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    添加节点到图谱
    
    在图谱中创建一个新节点。如果没有指定 node_id，系统会自动生成一个唯一ID。
    
    Args:
        node_type: 节点类型（如 "query", "evidence", "source" 等）
        attributes: 节点属性字典
        node_id: 节点ID（可选），如果不提供会自动生成
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的节点信息
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.add_node(node_type, attributes, node_id))


def upsert_node(
    node_type: str,
    attributes: dict[str, Any],
    dedupe_key: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    更新或插入节点
    
    如果节点已存在（通过 dedupe_key 匹配），则更新其属性；否则创建新节点。
    
    Args:
        node_type: 节点类型
        attributes: 节点属性字典
        dedupe_key: 去重键，通常是节点ID
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 更新或创建的节点信息
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.upsert_node(node_type, attributes, dedupe_key))


def add_edge(
    source_id: str,
    target_id: str,
    edge_type: str,
    attributes: Optional[dict[str, Any]] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    添加边（关系）到图谱
    
    在两个节点之间创建一条边，定义它们之间的关系。
    
    Args:
        source_id: 源节点ID
        target_id: 目标节点ID
        edge_type: 边类型（如 "has_query", "supported_by", "uses" 等）
        attributes: 边属性字典（可选）
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的边信息
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.add_edge(source_id, target_id, edge_type, attributes))


def get_node(
    node_id: str,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    根据ID获取节点
    
    从图谱中检索指定ID的节点信息。
    
    Args:
        node_id: 节点ID
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 节点信息，如果不存在返回空字典
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.get_node(node_id))


def search_nodes(
    node_type: str,
    filter: dict[str, Any],
    cache_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    搜索节点
    
    根据节点类型和过滤条件检索节点列表。
    
    Args:
        node_type: 节点类型
        filter: 过滤条件字典，键为属性名，值为属性值
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        list: 匹配条件的节点列表
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.search_node(node_type, filter))


def get_subgraph(
    node_id: str,
    depth: int = 2,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    获取子图（Ego-network）
    
    获取指定节点周围一定深度内的所有节点和边，形成子图。
    
    Args:
        node_id: 中心节点ID
        depth: 搜索深度，默认为2（直接邻居及其邻居）
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 包含 nodes 和 edges 的子图数据
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.get_subgraph(node_id, depth))


def save_graph(cache_dir: Optional[str] = None) -> None:
    """
    保存图谱到磁盘
    
    将当前内存中的图谱数据持久化到文件。
    
    Args:
        cache_dir: 缓存目录路径（可选）
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.save())


def create_user_request(
    request: str,
    research_goal: Optional[str] = None,
    language: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建用户请求节点
    
    创建一个表示用户研究请求的节点，包含用户输入的查询内容。
    
    Args:
        request: 用户请求文本
        research_goal: 研究目标（可选）
        language: 语言标识（可选），如 "zh" 或 "en"
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的用户请求节点
    """
    manager = _get_manager(cache_dir)
    attributes = {"request": request}
    if research_goal:
        attributes["research_goal"] = research_goal
    if language:
        attributes["language"] = language
    return _run_async(manager.add_node(NodeType.USER_REQUEST, attributes))


def create_query(
    text: str,
    status: str = "pending",
    parent_id: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建查询节点
    
    创建一个研究查询节点，用于表示一个需要搜索的问题或主题。
    
    Args:
        text: 查询文本内容
        status: 查询状态，默认为 "pending"（待处理）
        parent_id: 父节点ID（可选），用于建立层级关系
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的查询节点
    """
    manager = _get_manager(cache_dir)
    query_id = _run_async(manager.add_node(NodeType.QUERY, {"text": text, "status": status}))
    if parent_id:
        _run_async(manager.add_edge(parent_id, query_id, EdgeType.HAS_QUERY))
    return query_id


def create_source(
    url: str,
    title: Optional[str] = None,
    source_type: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建来源节点
    
    创建一个表示信息来源的节点，如网页、论文、文档等。
    
    Args:
        url: 来源URL地址
        title: 来源标题（可选）
        source_type: 来源类型（可选），如 "webpage", "paper", "github" 等
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的来源节点
    """
    manager = _get_manager(cache_dir)
    attributes = {"url": url}
    if title:
        attributes["title"] = title
    if source_type:
        attributes["source_type"] = source_type
    return _run_async(manager.add_node(NodeType.SOURCE, attributes))


def create_document(
    text: str,
    source_id: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建文档节点
    
    创建一个表示文档内容的节点，通常与来源节点关联。
    
    Args:
        text: 文档文本内容
        source_id: 来源节点ID（可选），建立文档与来源的关联
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的文档节点
    """
    manager = _get_manager(cache_dir)
    attributes = {"text": text}
    if source_id:
        attributes["source_id"] = source_id
    doc_id = _run_async(manager.add_node(NodeType.DOCUMENT, attributes))
    if source_id:
        _run_async(manager.add_edge(source_id, doc_id, EdgeType.HAS_DOCUMENT))
    return doc_id


def create_evidence(
    claim: str,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建证据节点
    
    创建一个表示证据的节点，用于支持或反驳某个主张（claim）。
    
    Args:
        claim: 证据支持的主张文本
        document_id: 文档节点ID（可选），表示证据来源于哪个文档
        source_id: 来源节点ID（可选），表示证据来源于哪个来源
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的证据节点
    """
    manager = _get_manager(cache_dir)
    evidence_id = _run_async(manager.add_node(NodeType.EVIDENCE, {"claim": claim, "status": "pending"}))
    if document_id:
        _run_async(manager.add_edge(document_id, evidence_id, EdgeType.EXTRACTED_STATEMENT))
    if source_id:
        _run_async(manager.add_edge(source_id, evidence_id, EdgeType.SUPPORTED_BY))
    return evidence_id


def create_conflict(
    description: str,
    evidence_ids: list[str],
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建冲突节点
    
    创建一个表示证据冲突的节点，用于记录多个证据之间的矛盾。
    
    Args:
        description: 冲突描述
        evidence_ids: 涉及冲突的证据节点ID列表
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的冲突节点
    """
    manager = _get_manager(cache_dir)
    conflict_id = _run_async(manager.add_node(NodeType.CONFLICT, {"description": description}))
    for evidence_id in evidence_ids:
        _run_async(manager.add_edge(conflict_id, evidence_id, EdgeType.HAS_CONFLICT))
    return conflict_id


def create_analysis(
    text: str,
    query_id: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建分析节点
    
    创建一个表示中间分析结果的节点，用于记录阶段性结论、框架或取舍方案。
    
    Args:
        text: 分析内容文本
        query_id: 查询节点ID（可选），表示该分析解决了哪个查询的问题
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的分析节点
    """
    manager = _get_manager(cache_dir)
    analysis_id = _run_async(manager.add_node(NodeType.ANALYSIS, {"text": text}))
    if query_id:
        _run_async(manager.add_edge(query_id, analysis_id, EdgeType.RESOLVES_GAP))
    return analysis_id


def create_report_section(
    title: str,
    content: str,
    section_type: Optional[str] = None,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    创建报告章节节点
    
    创建一个表示报告章节的节点，用于存储报告的各个章节内容。
    
    Args:
        title: 章节标题
        content: 章节内容
        section_type: 章节类型（可选），如 "introduction", "methodology", "conclusion" 等
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 创建的报告章节节点
    """
    manager = _get_manager(cache_dir)
    attributes = {"title": title, "content": content}
    if section_type:
        attributes["section_type"] = section_type
    return _run_async(manager.add_node(NodeType.REPORT_SECTION, attributes))


def bind_evidence_to_section(
    section_id: str,
    evidence_ids: list[str],
    claim_ids: Optional[list[str]] = None,
    cache_dir: Optional[str] = None
) -> None:
    """
    将证据绑定到报告章节
    
    建立报告章节与证据之间的引用关系，确保报告内容有证据支持。
    
    Args:
        section_id: 报告章节节点ID
        evidence_ids: 证据节点ID列表
        claim_ids: 主张节点ID列表（可选）
        cache_dir: 缓存目录路径（可选）
    """
    manager = _get_manager(cache_dir)
    for evidence_id in evidence_ids:
        _run_async(manager.add_edge(section_id, evidence_id, EdgeType.USES))
    if claim_ids:
        for claim_id in claim_ids:
            _run_async(manager.add_edge(section_id, claim_id, EdgeType.USES))


def get_pending_queries(
    cache_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    获取待处理的查询列表
    
    检索所有状态为 "pending" 的查询节点，用于调度处理。
    
    Args:
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        list: 待处理查询节点列表
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.search_node(NodeType.QUERY, {"status": "pending"}))


def get_query_subgraph(
    query_id: str,
    depth: int = 2,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    获取查询的子图
    
    获取指定查询节点及其相关的所有证据、文档、来源等形成的子图。
    
    Args:
        query_id: 查询节点ID
        depth: 搜索深度，默认为2
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 查询的子图数据
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.get_subgraph(query_id, depth))


def mark_query_status(
    query_id: str,
    status: str,
    cache_dir: Optional[str] = None
) -> dict[str, Any]:
    """
    更新查询状态
    
    修改查询节点的状态，如从 "pending" 变为 "completed" 或 "blocked"。
    
    Args:
        query_id: 查询节点ID
        status: 新状态
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 更新后的查询节点
    """
    manager = _get_manager(cache_dir)
    return _run_async(manager.upsert_node(NodeType.QUERY, {"status": status}, dedupe_key=query_id))


def list_graph_databases(cache_dir: Optional[str] = None) -> dict[str, Any]:
    """
    列出可用的图谱数据库
    
    扫描缓存目录，列出所有已保存的图谱数据库。
    
    Args:
        cache_dir: 缓存目录路径（可选）
    
    Returns:
        dict: 包含数据库列表和位置信息的字典
    """
    cache_path = Path(cache_dir) if cache_dir else get_default_graph_cache_dir()
    result = {"databases": [], "location": str(cache_path)}
    try:
        if cache_path.exists():
            files = list(cache_path.glob("*.jsonl"))
            for file in files:
                if file.name == "research_graph.jsonl":
                    result["databases"].append("default")
                elif file.name.startswith("research_graph-") and file.name.endswith(".jsonl"):
                    result["databases"].append(file.name[15:-6])
    except (OSError, PermissionError):
        result["databases"] = []
    return result