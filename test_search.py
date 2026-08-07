"""简化的搜索质量测试脚本
直接调用 Tavily API，对比不同查询策略的搜索结果质量
"""

import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from tavily import TavilyClient

# 加载环境变量
load_dotenv()

# 测试配置
OUTPUT_DIR = Path("outputs/search_test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 测试查询变体 - 从简单到精准
TEST_QUERIES = [
    {
        "name": "V1_basic",
        "query": "Ring of Nestor",
        "description": "最基础的查询，只有实体名称"
    },
    {
        "name": "V2_with_context",
        "query": "Ring of Nestor Mycenaean gold ring",
        "description": "添加基本上下文（迈锡金戒指）"
    },
    {
        "name": "V3_specific_identifiers",
        "query": "Ring of Nestor Arthur Evans Ashmolean Museum",
        "description": "添加唯一标识符（发现者+收藏机构）"
    },
    {
        "name": "V4_with_source_type",
        "query": "Ring of Nestor Arthur Evans Ashmolean Museum gold signet ring museum collection",
        "description": "添加来源类型限定（museum collection）"
    },
    {
        "name": "V5_academic_focus",
        "query": "Ring of Nestor Arthur Evans 1925 gold signet ring scholarly publication",
        "description": "添加具体年份和学术来源限定"
    }
]


def run_search(query: str, mode: str = "basic", max_results: int = 5) -> dict:
    """执行 Tavily 搜索"""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    
    kwargs = {
        "query": query,
        "max_results": max_results,
        "include_raw_content": True,
        "topic": "general",
    }
    
    if mode == "advanced":
        kwargs["search_mode"] = "advanced"
    
    response = client.search(**kwargs)
    return response


def analyze_results(results: list) -> dict:
    """分析搜索结果质量"""
    analysis = {
        "total_results": len(results),
        "high_quality_sources": 0,
        "medium_quality_sources": 0,
        "low_quality_sources": 0,
        "has_wikipedia": False,
        "has_museum": False,
        "has_academic": False,
        "has_news": False,
        "source_domains": [],
    }
    
    high_quality_patterns = [".edu", ".ac.uk", ".org", "museum", "academic", "scholarly", "journal"]
    medium_quality_patterns = [".com", ".net", ".gov", "wikipedia"]
    low_quality_patterns = ["instagram", "facebook", "twitter", "blog", "wordpress"]
    
    for result in results:
        url = result.get("url", "").lower()
        title = result.get("title", "").lower()
        content = result.get("content", "").lower()
        
        analysis["source_domains"].append(url)
        
        # 质量分级
        if any(p in url for p in high_quality_patterns) or any(p in title + content for p in ["journal", "scholarly", "academic"]):
            analysis["high_quality_sources"] += 1
        elif any(p in url for p in medium_quality_patterns):
            analysis["medium_quality_sources"] += 1
        else:
            analysis["low_quality_sources"] += 1
        
        # 特定来源类型
        if "wikipedia" in url:
            analysis["has_wikipedia"] = True
        if "museum" in url or "museum" in title:
            analysis["has_museum"] = True
        if any(p in url for p in [".edu", ".ac.uk", "academic", "scholarly"]):
            analysis["has_academic"] = True
        if any(p in url for p in [".com", ".net"]) and not any(p in url for p in low_quality_patterns):
            analysis["has_news"] = True
    
    return analysis


def generate_report(all_results: list) -> str:
    """生成 markdown 对比报告"""
    report = f"""# 搜索质量测试报告

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**测试目标**: Ring of Nestor 搜索查询优化

---

## 测试概览

共测试 **{len(all_results)}** 种查询变体，对比 basic 和 advanced 两种搜索模式。

---

## 查询变体详情

"""
    
    for result in all_results:
        report += f"""### {result['name']} ({result['mode']} 模式)

**查询文本**: `{result['query']}`
**描述**: {result['description']}

#### 结果质量分析

| 指标 | 值 |
|------|-----|
| 返回结果数 | {result['analysis']['total_results']} |
| 高质量来源 | {result['analysis']['high_quality_sources']} |
| 中等质量来源 | {result['analysis']['medium_quality_sources']} |
| 低质量来源 | {result['analysis']['low_quality_sources']} |
| 包含 Wikipedia | {'✅ 是' if result['analysis']['has_wikipedia'] else '❌ 否'} |
| 包含博物馆来源 | {'✅ 是' if result['analysis']['has_museum'] else '❌ 否'} |
| 包含学术来源 | {'✅ 是' if result['analysis']['has_academic'] else '❌ 否'} |
| 包含新闻来源 | {'✅ 是' if result['analysis']['has_news'] else '❌ 否'} |

#### 返回结果列表

"""
        
        for i, item in enumerate(result.get("results", []), 1):
            title = item.get("title", "N/A")
            url = item.get("url", "N/A")
            score = item.get("score", "N/A")
            content_text = item.get("content") or ""
            raw_content_text = item.get("raw_content") or ""
            content_preview = content_text[:200].replace("\n", " ")
            raw_content_len = len(raw_content_text)
            
            report += f"""**{i}. {title}**
- **URL**: {url}
- **Score**: {score:.4f}
- **Content 长度**: {len(item.get('content', ''))} 字符
- **Raw Content 长度**: {raw_content_len} 字符
- **Content 预览**: {content_preview}...

"""
    
    # 总结对比
    report += """---

## 对比总结

### 各查询变体评分

| 查询 | 模式 | 结果数 | 高质量源 | 博物馆源 | 学术源 | Wiki | 总体评价 |
|------|------|--------|----------|----------|--------|------|----------|
"""
    
    for result in all_results:
        a = result["analysis"]
        score = "⭐⭐⭐⭐⭐" if a["high_quality_sources"] >= 3 else "⭐⭐⭐⭐" if a["high_quality_sources"] >= 2 else "⭐⭐⭐" if a["high_quality_sources"] >= 1 else "⭐⭐" if a["medium_quality_sources"] >= 1 else "⭐"
        
        report += f"| {result['name']} | {result['mode']} | {a['total_results']} | {a['high_quality_sources']} | {'✅' if a['has_museum'] else '❌'} | {'✅' if a['has_academic'] else '❌'} | {'✅' if a['has_wikipedia'] else '❌'} | {score} |\n"
    
    report += """
### 改进建议

1. **查询策略优化**:
   - 添加具体人名（如 Arthur Evans）可以显著提升结果相关性
   - 添加收藏机构（如 Ashmolean Museum）可以直接定位权威来源
   - 避免堆砌泛化关键词（如 "archaeological study museum collection"）

2. **搜索模式选择**:
   - Advanced 模式可能返回更多相关结果
   - 可以考虑使用 `search_depth="advanced"` 而非默认的 basic 模式

3. **来源类型过滤**:
   - 优先关注 `.edu`、`.ac.uk`、`.org` 等学术域名
   - 博物馆官方网站通常提供最权威的藏品信息
   - 排除社交媒体和低质量博客内容

4. **多轮搜索策略**:
   - 第一轮使用精准标识符定位核心来源
   - 第二轮从核心来源的引用中发现更多线索
   - 第三轮针对缺失的具体信息进行补充搜索

---

*报告由 test_search.py 自动生成*
"""
    
    return report


def main():
    """主测试函数"""
    print("=" * 60)
    print("开始搜索质量测试...")
    print("=" * 60)
    
    all_results = []
    
    # 测试 basic 模式
    print("\n📋 测试 Basic 模式")
    print("-" * 40)
    for query_var in TEST_QUERIES:
        print(f"\n🔍 测试: {query_var['name']}")
        print(f"   查询: {query_var['query']}")
        
        try:
            response = run_search(query_var["query"], mode="basic", max_results=5)
            results = response.get("results", [])
            analysis = analyze_results(results)
            
            result_entry = {
                "name": query_var["name"],
                "query": query_var["query"],
                "description": query_var["description"],
                "mode": "basic",
                "results": results,
                "analysis": analysis
            }
            all_results.append(result_entry)
            
            print(f"   ✅ 返回 {len(results)} 条结果")
            print(f"   📊 高质量: {analysis['high_quality_sources']}, 中等: {analysis['medium_quality_sources']}, 低质量: {analysis['low_quality_sources']}")
            print(f"   🏛️ 博物馆源: {'是' if analysis['has_museum'] else '否'}, 🎓 学术源: {'是' if analysis['has_academic'] else '否'}")
            
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            all_results.append({
                "name": query_var["name"],
                "query": query_var["query"],
                "description": query_var["description"],
                "mode": "basic",
                "results": [],
                "analysis": {"error": str(e)}
            })
    
    # 测试 advanced 模式（选择表现最好的 3 个查询）
    print("\n📋 测试 Advanced 模式")
    print("-" * 40)
    advanced_queries = [TEST_QUERIES[0], TEST_QUERIES[2], TEST_QUERIES[4]]
    
    for query_var in advanced_queries:
        print(f"\n🔍 测试: {query_var['name']} (Advanced)")
        print(f"   查询: {query_var['query']}")
        
        try:
            response = run_search(query_var["query"], mode="advanced", max_results=5)
            results = response.get("results", [])
            analysis = analyze_results(results)
            
            result_entry = {
                "name": f"{query_var['name']}_adv",
                "query": query_var["query"],
                "description": f"{query_var['description']} (Advanced 模式)",
                "mode": "advanced",
                "results": results,
                "analysis": analysis
            }
            all_results.append(result_entry)
            
            print(f"   ✅ 返回 {len(results)} 条结果")
            print(f"   📊 高质量: {analysis['high_quality_sources']}, 中等: {analysis['medium_quality_sources']}, 低质量: {analysis['low_quality_sources']}")
            print(f"   🏛️ 博物馆源: {'是' if analysis['has_museum'] else '否'}, 🎓 学术源: {'是' if analysis['has_academic'] else '否'}")
            
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            all_results.append({
                "name": f"{query_var['name']}_adv",
                "query": query_var["query"],
                "description": query_var["description"],
                "mode": "advanced",
                "results": [],
                "analysis": {"error": str(e)}
            })
    
    # 保存原始结果
    raw_output_file = OUTPUT_DIR / "raw_results.json"
    with open(raw_output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 原始结果已保存: {raw_output_file}")
    
    # 生成报告
    print("\n📝 生成对比报告...")
    report = generate_report(all_results)
    
    report_file = OUTPUT_DIR / "search_results.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 报告已保存: {report_file}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print(f"\n📂 所有输出文件位于: {OUTPUT_DIR}")
    print(f"   - search_results.md: 对比报告")
    print(f"   - raw_results.json: 原始结果")


if __name__ == "__main__":
    main()
