from memory.graph import GraphManager
from prompts.memory_manager_prompts import *
from langchain.chat_models import init_chat_model

class MemoryManager:
    def __init__(self, config: dict):
        self.config = config  # 每个 Agent 单独配置 config
        self.graph = GraphManager(config.get("graph_path"))
        self.model = init_chat_model(
            self.config.get("model_name", "gpt-5.1"),
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 2048),
            max_retries=self.config.get("max_retries", 3),
        )

    # -----------------------------
    # Orchestrator 调用  
    # -----------------------------
    def init_research(self, user_request: str) -> dict:
        """基于用户请求初始化研究图谱

        Args:
            user_request (str): The original research request from the user

        Returns:
            dict: To be defined
        """
        # 解析用户请求，提取研究目标、语言要求、初始查询等信息
        response = self.model.invoke(
            init_research.format(user_request=user_request)
        )

        user_request_id = self.graph.add_node(
            "user_request",
            {
                "request": user_request,
                "research_goal": response.get("research_goal", ""),
                "language": response.get("language", "en"),
            },
        )

        initial_queries = response.get("initial_queries", None)

        # TODO 加入护栏，处理没有正确生成初始查询的情况
        for query in initial_queries:
            query_id = self.graph.add_node(
                "query", {"text": query, "status": "pending"}
            )
            self.graph.add_edge(user_request_id, query_id, "has_query")

        return {} # TODO 返回什么内容给 Orchestrator？
    
    def analyze_subgraph(self, query: str) -> dict:...
        
    def get_next_queries(self, limit: int = 4) -> list[dict]: ...
    # 判断是否收敛，以及是否需要添加新的查询
    def analyze_query_state(self, query: str) -#> dict: ...
    def add_followup_query(self, parent_query_id: str, query_text: str, expansion_type: str, reason: str) -> str: ...
    def mark_query(self, query_id: str, status: str, **metrics): ...

    # -----------------------------
    # Orchestrator 调用  END
    # -----------------------------
    
    
    # -----------------------------
    # Searcher 调用  
    # -----------------------------
    def get_query_context(self, query_id: str) -> dict: ...
    
    def submit_search_result(self, query_id: str, search_result: dict) -> dict:
        """处理 Searcher 提交的搜索结果，更新图谱并提供反馈

        Args:
            query_id (str): The ID of the query this search result corresponds to
            search_result (dict): The search results, including found sources and metadata

        Returns:
            dict: Feedback for the Searcher, e.g. whether to continue, refine, or stop
        """
        
        # TODO 考虑如何维护 source 信息
        document, source = search_result.get("document"), search_result.get("source")
        document_id = self.graph.add_node("document", {"text": document, "source": source})
        
        extracted_info = self.extract_content(document)
        # TODO keywords 是否需要？
        keywords, statements, summary = extracted_info.get("keywords"), extracted_info.get("statement"), extracted_info.get("summary")
        for statement in statements:
            # ? 是否有必要把 statement 和 source 关联起来？目前设计是 document -> extracted_statement -> statement, 但也可以直接 document -> statement
            statement_id = self.graph.add_node("statement", {"text": statement, "source": source})
            self.graph.add_edge(document_id, statement_id, "extracted_statement")
        summary_id = self.graph.add_node("summary", {"text": summary})
        self.graph.add_edge(document_id, summary_id, "has_summary")
        
        return {} # TODO 需要返回什么内容给 Searcher？
    
    # -----------------------------
    # Searcher 调用  END
    # -----------------------------


    # -----------------------------
    # Reporter 调用  
    # -----------------------------
    def export_report_context(self, goal_id: str) -> dict: ...
    def bind_report_section(self, section: dict, claim_ids: list[str], evidence_ids: list[str]) -> str: ...
    
    # -----------------------------
    # Reporter 调用  END
    # -----------------------------

    # 内部辅助
    def extract_content(self, content: str) -> dict:
        """Extract semantic metadata from document content using LLM.

        Uses a language model to understand the content and extract:
        - Keywords: Important terms and concepts
        - Statement: Key insights or conclusions
        - Summary: Concise summary of the whole document content

        Args:
            content (str): The text content to extract

        Returns:
            Dict: Contains extracted metadata with keys:
                - keywords: List[str]
                - statement: List[str]
                - summary: str
        """
        prompt = extract_content + content
        try:
            response = self.model.invoke(prompt)
            return response
        except Exception as e:
            print(f"Error extracting content: {e}")
            return {}
        
        
    # ? 要把 subgraph_summary 加入图中吗？
    def summarize_subgraph(self, node_id: str) -> dict:
        """Summarize a subgraph around a given node to extract key insights and context.

        Args:
            node_id (str): The ID of the node to summarize
        Returns:
            dict: To be defined
        """
        subgraph = self.graph.get_subgraph(node_id, depth=2)
        
        context = self.model.invoke(summarize_subgraph.format(subgraph=subgraph))
        
        return {}
    
    # ? 是否需要去重功能？ 当前仅将 source 作为 document 的一个属性，并且没有维护 Document 内部 Source 信息
    def deduplicate_source(self, source: dict) -> str | None: ...
