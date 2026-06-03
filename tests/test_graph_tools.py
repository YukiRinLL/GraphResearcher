#!/usr/bin/env python3
"""
测试 graph_tools.py 的功能
"""

import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tools.graph_tools import (
    create_user_request,
    create_query,
    create_source,
    create_document,
    create_evidence,
    create_conflict,
    create_analysis,
    create_report_section,
    bind_evidence_to_section,
    get_pending_queries,
    get_query_subgraph,
    mark_query_status,
    get_node,
    list_graph_databases,
    save_graph,
    clear_manager_cache
)

def test_basic_operations():
    """测试基础的图谱操作"""
    print("=" * 60)
    print("测试 1: 创建用户请求和查询")
    print("=" * 60)
    
    # 1. 创建用户请求
    user_request = create_user_request(
        request="研究人工智能的发展趋势",
        research_goal="了解AI在过去10年的发展历程和未来方向",
        language="zh"
    )
    print(f"✓ 创建用户请求: {user_request}")
    
    # 2. 创建查询
    query1 = create_query(
        text="AI发展历程 2014-2024",
        parent_id=user_request
    )
    print(f"✓ 创建查询1: {query1}")
    
    query2 = create_query(
        text="AI未来发展趋势预测",
        parent_id=user_request
    )
    print(f"✓ 创建查询2: {query2}")
    
    print()
    print("=" * 60)
    print("测试 2: 创建来源、文档和证据")
    print("=" * 60)
    
    # 3. 创建来源
    source1 = create_source(
        url="https://example.com/ai-trends",
        title="人工智能发展报告",
        source_type="webpage"
    )
    print(f"✓ 创建来源1: {source1}")
    
    # 4. 创建文档
    doc1 = create_document(
        text="人工智能在过去10年快速发展，特别是深度学习技术的突破。"
             "GPT系列模型在2020年后迅速崛起，改变了自然语言处理领域。",
        source_id=source1
    )
    print(f"✓ 创建文档1: {doc1}")
    
    # 5. 创建证据
    evidence1 = create_evidence(
        claim="AI发展在过去10年加速，主要驱动力是深度学习",
        document_id=doc1,
        source_id=source1
    )
    print(f"✓ 创建证据1: {evidence1}")
    
    evidence2 = create_evidence(
        claim="GPT系列模型在2020年后对NLP领域产生重大影响",
        document_id=doc1,
        source_id=source1
    )
    print(f"✓ 创建证据2: {evidence2}")
    
    print()
    print("=" * 60)
    print("测试 3: 创建冲突和分析")
    print("=" * 60)
    
    # 6. 创建另一个来源和冲突证据
    source2 = create_source(
        url="https://example.com/ai-skeptic",
        title="AI发展的不同观点",
        source_type="webpage"
    )
    print(f"✓ 创建来源2: {source2}")
    
    doc2 = create_document(
        text="有人认为AI的发展被过度炒作，实际进展有限。",
        source_id=source2
    )
    print(f"✓ 创建文档2: {doc2}")
    
    evidence3 = create_evidence(
        claim="AI发展被过度炒作，实际进展有限",
        document_id=doc2,
        source_id=source2
    )
    print(f"✓ 创建证据3: {evidence3}")
    
    # 7. 创建冲突
    conflict1 = create_conflict(
        description="关于AI发展速度的两种观点冲突",
        evidence_ids=[evidence1, evidence3]
    )
    print(f"✓ 创建冲突1: {conflict1}")
    
    # 8. 创建分析
    analysis1 = create_analysis(
        text="AI发展确实取得了显著进展，但也存在一定炒作。需要理性看待。",
        query_id=query1
    )
    print(f"✓ 创建分析1: {analysis1}")
    
    print()
    print("=" * 60)
    print("测试 4: 创建报告章节并绑定证据")
    print("=" * 60)
    
    # 9. 创建报告章节
    section1 = create_report_section(
        title="AI发展历程",
        content="人工智能在过去10年经历了快速发展，深度学习技术是主要驱动力。",
        section_type="introduction"
    )
    print(f"✓ 创建报告章节1: {section1}")
    
    # 10. 绑定证据到章节
    bind_evidence_to_section(
        section_id=section1,
        evidence_ids=[evidence1, evidence2]
    )
    print("✓ 绑定证据到报告章节")
    
    print()
    print("=" * 60)
    print("测试 5: 查询和更新操作")
    print("=" * 60)
    
    # 11. 获取待处理查询
    pending_queries = get_pending_queries()
    print(f"✓ 待处理查询: {len(pending_queries)} 个")
    for q in pending_queries:
        print(f"  - {q}")
    
    # 12. 标记查询为已完成
    updated_query1 = mark_query_status(query1, "completed")
    print(f"✓ 更新查询状态: {updated_query1}")
    
    # 13. 获取查询的子图
    query_subgraph = get_query_subgraph(query1)
    print(f"✓ 查询子图: {len(query_subgraph['nodes'])} 个节点, {len(query_subgraph['edges'])} 条边")
    
    # 14. 获取节点详情
    node_details = get_node(evidence1)
    print(f"✓ 获取证据节点详情: {node_details}")
    
    print()
    print("=" * 60)
    print("测试 6: 列出图谱数据库")
    print("=" * 60)
    
    databases = list_graph_databases()
    print(f"✓ 图谱存储位置: {databases['location']}")
    print(f"✓ 可用数据库: {databases['databases']}")
    
    # 15. 保存图谱
    save_graph()
    print("✓ 图谱已保存到磁盘")
    
    print()
    print("=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)
    
    # 清理缓存
    clear_manager_cache()

if __name__ == "__main__":
    print("\n开始测试 graph_tools.py...\n")
    try:
        test_basic_operations()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
