import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tools import graph_tools, report_tools  # noqa: E402


def test_prepare_report_chapter_bundle_uses_slot_based_evidence(tmp_path, monkeypatch):
    report_tools.commit_report_outline(
        str(tmp_path),
        "Test Report",
        [
            {
                "chapter_id": 1,
                "title": "Overview",
                "goals": ["summarize"],
                "slot_keys": ["lead-slot"],
                "section_plan": "lead paragraph",
            }
        ],
    )
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [{"id": "goal", "type": "UserRequest"}] if kind == "user_request" else ([{"id": "s1", "type": "Source", "url": "https://example.com", "title": "Example"}] if kind == "source" else []))
    monkeypatch.setattr(graph_tools, "get_coverage_slots", lambda goal_id: [{"id": "slot-1", "type": "CoverageSlot", "slot_key": "lead-slot", "section": "lead"}])
    monkeypatch.setattr(graph_tools, "get_slot_fillers", lambda slot_id: {"claims": [{"id": "claim-1", "type": "Claim", "text": "lead fact"}], "evidence": []})
    monkeypatch.setattr(graph_tools, "get_all_nodes", lambda: [
        {"id": "claim-1", "type": "Claim", "text": "lead fact"},
        {"id": "doc-1", "type": "Document"},
        {"id": "s1", "type": "Source", "url": "https://example.com", "title": "Example"},
    ])
    monkeypatch.setattr(graph_tools, "get_all_edges", lambda: [
        {"source": "doc-1", "target": "claim-1", "type": "CLAIMED_BY"},
        {"source": "s1", "target": "doc-1", "type": "HAS_DOCUMENT"},
    ])

    bundle = report_tools.prepare_report_chapter_bundle(str(tmp_path), 1)

    assert bundle["status"] == "ok"
    assert bundle["slot_keys"] == ["lead-slot"]
    assert bundle["slot_ids"] == ["slot-1"]
    assert bundle["evidence_items"][0]["text"] == "lead fact"


def test_commit_report_outline_persists_slot_keys(tmp_path):
    result = report_tools.commit_report_outline(
        str(tmp_path),
        "Outline",
        [
            {
                "chapter_id": 1,
                "title": "History",
                "goals": ["cover history"],
                "slot_keys": ["history-slot"],
                "section_plan": "history section",
            }
        ],
    )

    outline = json.loads((tmp_path / ".report_outline.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert outline["chapters"][0]["slot_keys"] == ["history-slot"]
