import logging

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from memory.graph import GraphManager
from prompts.memory_manager_prompts import extract_content

logger = logging.getLogger(__name__)

EXTRACT_CONTENT_SCHEMA = {
    "title": "ContentExtractionResult",
    "description": "Structured semantic metadata extracted from document content.",
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "description": "Important terms and concepts, ordered from most to least important.",
            "items": {"type": "string"},
        },
        "context": {
            "type": "string",
            "description": "One sentence describing the main topic, key points, and purpose.",
        },
        "tags": {
            "type": "array",
            "description": "Broad classification categories and themes.",
            "items": {"type": "string"},
        },
        "statement": {
            "type": "array",
            "description": "Key insights or conclusions drawn from the content.",
            "items": {"type": "string"},
        },
        "summary": {
            "type": "string",
            "description": "A concise summary of the whole document content.",
        },
    },
    "required": ["keywords", "context", "tags", "statement", "summary"],
    "additionalProperties": False,
}


class MemoryManager:
    def __init__(self, config: dict):
        self.config = config  # 每个 Agent 单独配置 config
        self.memories = {}
        self.model = init_chat_model(
            self.config.get("model_name", "gpt-5.1"),
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 2048),
            max_retries=self.config.get("max_retries", 6),
        )
        self.analysis_model = self.model.with_structured_output(
            EXTRACT_CONTENT_SCHEMA,
            method="json_schema",
            strict=True,
        )
        
        self.agent = create_agent(
            model=self.model,
        )
        self.graph = GraphManager()

    def extract_content(self, content: str) -> dict:
        """Extract semantic metadata from document content using LLM.

        Uses a language model to understand the content and extract:
        - Keywords: Important terms and concepts
        - Context: Overall domain or theme
        - Tags: Classification categories
        - Statement: Key insights or conclusions
        - Summary: Concise summary of the whole document content

        Args:
            content (str): The text content to extract

        Returns:
            Dict: Contains extracted metadata with keys:
                - keywords: List[str]
                - context: str
                - tags: List[str]
                - statement: List[str]
                - summary: str
        """
        prompt = extract_content + content
        try:
            response = self.analysis_model.invoke(prompt)
            return response
        except Exception:
            logger.exception("Error occurred while extracting content")
            return {}
        
    def summary_subgraph(self, node_id: str) -> dict:
        """
            Summarize the content of the subgraph of the given node in the knowledge graph.
        """
        
    def add_memory(self, content: str, metadata: dict, **kwargs):
        """
            Add a new memory to the knowledge graph, including content, metadata, and relationships.
        """

    def find_related_nodes(self, content: str, node_type: str, top_k: int = 5) -> list:
        """
            Find related nodes in the knowledge graph based on the content and node type, returning the top K most relevant nodes.
        """
    
    def find_nodes_by_keyword(self, keyword: str) -> list:
        pass