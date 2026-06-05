"""
Simple script to query and display the graph structure from Neo4j
"""
import os
import asyncio
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

# Load environment variables
load_dotenv()

# Neo4j connection config from environment variables
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")

async def view_graph():
    driver = AsyncGraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    
    async with driver.session() as session:
        # Query 1: Get all nodes count by type (label)
        print("=" * 80)
        print("节点统计 (按标签类型)")
        print("=" * 80)
        result = await session.run("""
            MATCH (n)
            UNWIND labels(n) as label
            WITH label, count(DISTINCT n) AS count
            ORDER BY count DESC
            RETURN label, count
        """)
        records = await result.data()
        for record in records:
            print(f"{record['label']:20s}: {record['count']} 个节点")
        
        # Query 2: Get all relationships count by type
        print("\n" + "=" * 80)
        print("关系统计 (按类型)")
        print("=" * 80)
        result = await session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            ORDER BY count DESC
        """)
        records = await result.data()
        for record in records:
            print(f"{record['type']:20s}: {record['count']} 个关系")
        
        # Query 3: Get sample nodes of each type
        print("\n" + "=" * 80)
        print("节点示例 (每种类型前 3 个)")
        print("=" * 80)
        result = await session.run("""
            MATCH (n)
            UNWIND labels(n) as label
            WITH label, collect(DISTINCT n) AS nodes
            UNWIND nodes[0..3] AS sample
            RETURN label, sample.id AS id, 
                   coalesce(sample.text, sample.request, sample.title, 'N/A') as content
            ORDER BY label
        """)
        records = await result.data()
        current_type = None
        for record in records:
            if record['label'] != current_type:
                current_type = record['label']
                print(f"\n[{current_type}]:")
            
            content = record['content']
            if len(content) > 100:
                content = content[:100] + "..."
            print(f"  - ID: {record['id']}")
            print(f"    内容：{content}")
        
        # Query 4: Get graph structure for latest goal
        print("\n" + "=" * 80)
        print("最新研究目标的图谱结构")
        print("=" * 80)
        result = await session.run("""
            MATCH (goal:UserRequest)
            WITH goal ORDER BY goal.id DESC LIMIT 1
            MATCH path = (goal)-[*1..3]-(related)
            RETURN 
                goal.id AS goal_id,
                coalesce(goal.request, '') AS goal_request,
                count(DISTINCT related) AS related_nodes,
                count(DISTINCT relationships(path)) AS relationships
        """)
        records = await result.data()
        if records:
            record = records[0]
            goal_request = record['goal_request']
            if len(goal_request) > 100:
                goal_request = goal_request[:100] + "..."
            print(f"研究目标 ID: {record['goal_id']}")
            print(f"研究目标：{goal_request}")
            print(f"相关节点数：{record['related_nodes']}")
            print(f"关系数：{record['relationships']}")
        
        # Query 5: Get detailed subgraph for latest goal
        print("\n" + "=" * 80)
        print("详细子图结构（最新目标）")
        print("=" * 80)
        result = await session.run("""
            MATCH (goal:UserRequest)
            WITH goal ORDER BY goal.id DESC LIMIT 1
            OPTIONAL MATCH (goal)-[:HAS_QUERY]->(query:Query)
            OPTIONAL MATCH (query)-[:SEARCHED_BY]->(search_run:SearchRun)
            OPTIONAL MATCH (search_run)-[:FOUND_SOURCE]->(source:Source)
            OPTIONAL MATCH (source)-[:HAS_DOCUMENT]->(doc:Document)
            OPTIONAL MATCH (doc)-[:EXTRACTED_STATEMENT]->(evidence:Evidence)
            RETURN 
                goal.id AS goal_id,
                collect(DISTINCT query.id) AS query_ids,
                collect(DISTINCT search_run.id) AS search_run_ids,
                collect(DISTINCT source.id) AS source_ids,
                collect(DISTINCT doc.id) AS doc_ids,
                collect(DISTINCT evidence.id) AS evidence_ids
        """)
        records = await result.data()
        if records:
            record = records[0]
            print(f"研究目标：{record['goal_id']}")
            print(f"  Query 节点：{len(record['query_ids'])} 个")
            print(f"  Search Run 节点：{len(record['search_run_ids'])} 个")
            print(f"  Source 节点：{len(record['source_ids'])} 个")
            print(f"  Document 节点：{len(record['doc_ids'])} 个")
            print(f"  Evidence 节点：{len(record['evidence_ids'])} 个")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(view_graph())