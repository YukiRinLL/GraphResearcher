"""Lightweight Research Graph schema declarations.

The runtime still accepts legacy graph shapes while the evidence layer is
migrating, so this module is intentionally declarative first. New evidence-layer
helpers should align with these contracts; broader hard validation can be added
after historical runs and tests are migrated.
"""

NODE_REQUIRED_FIELDS = {
    "Source": {"url"},
    "Document": {"text", "source_id"},
    "Statement": {"text", "document_id", "statement_key"},
    "Evidence": {"text", "document_id", "evidence_key"},
    "Claim": {"canonical_text", "claim_key"},
}

EVIDENCE_LAYER_EDGES = {
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
