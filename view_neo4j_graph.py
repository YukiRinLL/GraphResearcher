"""
Simple script to query and display the graph structure from Neo4j
"""
import asyncio
from neo4j import AsyncGraphDatabase

# Neo4j connection config
URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "LUOCANYU"

async def view_graph():
    driver = AsyncGraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    
    async with driver.session() as session:
        # Query 1: Get all nodes count by type
        print("=" * 80)
        print("节点统计 (按类型)")
        print("=" * 80)
        result = await session.run("""
            MATCH (n:Node)
            RETURN n.type AS type, count(n) AS count
            ORDER BY count DESC
        """)
        records = await result.data()
        for record in records:
            print(f"{record['type']:20s}: {record['count']} 个节点")
        
        # Query 2: Get all relationships count by type
        print("\n" + "=" * 80)
        print("关系统计 (按类型)")
        print("=" * 80)
        result = await session.run("""
            MATCH ()-[r:RELATIONSHIP]->()
            RETURN r.type AS type, count(r) AS count
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
            MATCH (n:Node)
            WITH n.type AS type, collect(n) AS nodes
            UNWIND nodes[0..3] AS sample
            RETURN type, sample.id AS id, sample.text AS text, sample.request AS request
            ORDER BY type
        """)
        records = await result.data()
        current_type = None
        for record in records:
            if record['type'] != current_type:
                current_type = record['type']
                print(f"\n[{current_type}]:")
            
            content = record['text'] or record['request'] or 'N/A'
            if len(content) > 100:
                content = content[:100] + "..."
            print(f"  - ID: {record['id']}")
            print(f"    内容：{content}")
        
        # Query 4: Get graph structure for latest goal
        print("\n" + "=" * 80)
        print("最新研究目标的图谱结构")
        print("=" * 80)
        result = await session.run("""
            MATCH (goal:Node {type: 'user_request'})
            WITH goal ORDER BY goal.id DESC LIMIT 1
            MATCH path = (goal)-[*1..3]-(related)
            RETURN 
                goal.id AS goal_id,
                goal.request AS goal_request,
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
            MATCH (goal:Node {type: 'user_request'})
            WITH goal ORDER BY goal.id DESC LIMIT 1
            OPTIONAL MATCH (goal)-[r1:RELATIONSHIP {type: 'has_query'}]->(query:Node {type: 'query'})
            OPTIONAL MATCH (query)-[r2:RELATIONSHIP {type: 'searched_by'}]->(search_run:Node {type: 'search_run'})
            OPTIONAL MATCH (search_run)-[r3:RELATIONSHIP {type: 'found_source'}]->(source:Node {type: 'source'})
            OPTIONAL MATCH (source)-[r4:RELATIONSHIP {type: 'has_document'}]->(doc:Node {type: 'document'})
            OPTIONAL MATCH (doc)-[r5:RELATIONSHIP {type: 'extracted_statement'}]->(evidence:Node {type: 'evidence'})
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
