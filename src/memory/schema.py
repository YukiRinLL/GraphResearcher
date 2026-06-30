"""Lightweight Research Graph schema declarations.

The runtime still accepts legacy graph shapes while the evidence layer is
migrating, so this module is intentionally declarative first. New evidence-layer
helpers should align with these contracts; broader hard validation can be added
after historical runs and tests are migrated.
"""

NODE_REQUIRED_FIELDS = {
    "TaskContract": {"deliverable_type", "target_shape"},
    "CoverageSlot": {"slot_key", "status"},
    "ResearchFrontier": {"frontier_type", "status", "description"},
    "DimensionHypothesis": {"dimension_label", "parent_query_id"},
    "Source": {"url"},
    "Document": {"text", "source_id"},
    "Statement": {"text", "document_id", "statement_key"},
    "Evidence": {"text", "document_id", "evidence_key"},
    "Claim": {"canonical_text", "claim_key"},
}

EVIDENCE_LAYER_EDGES = {
    ("UserRequest", "HAS_TASK_CONTRACT", "TaskContract"),
    ("TaskContract", "HAS_COVERAGE_SLOT", "CoverageSlot"),
    ("UserRequest", "HAS_COVERAGE_SLOT", "CoverageSlot"),
    ("Query", "HAS_FRONTIER", "ResearchFrontier"),
    ("UserRequest", "HAS_FRONTIER", "ResearchFrontier"),
    ("Query", "TARGETS_SLOT", "CoverageSlot"),
    ("Evidence", "FILLS_SLOT", "CoverageSlot"),
    ("Claim", "FILLS_SLOT", "CoverageSlot"),
    ("ReportSection", "DERIVES_FROM_SLOT", "CoverageSlot"),
    ("ResearchFrontier", "ANCHORS_CLAIM", "Claim"),
    ("ResearchFrontier", "ANCHORS_CONFLICT", "Conflict"),
    ("ResearchFrontier", "ANCHORS_EVIDENCE", "Evidence"),
    ("DimensionHypothesis", "COVERS_DIMENSION", "Query"),
    ("Source", "HAS_DOCUMENT", "Document"),
    ("Document", "EXTRACTED_STATEMENT", "Statement"),
    ("Document", "HAS_EVIDENCE", "Evidence"),
    ("Statement", "NORMALIZED_TO", "Claim"),
    ("Evidence", "SUPPORTED_BY", "Claim"),
    ("Evidence", "CONTRADICTED_BY", "Claim"),
    ("Evidence", "QUALIFIED_BY", "Claim"),
    ("Claim", "HAS_ANALYSIS", "Analysis"),
    ("Statement", "INVOLVED_IN", "Analysis"),
    ("Evidence", "INVOLVED_IN", "Analysis"),
    ("Claim", "INVOLVED_IN", "Analysis"),
}
