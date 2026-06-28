"""Regression checks for Searcher result triage before extraction."""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

from agents import searcher  # noqa: E402


def main():
    core_query = '"Ring of Nestor" provenance authenticity'
    reception_query = '"Ring of Nestor" modern public reception social media'

    payload = {
        "results": [
            {
                "title": "Ring of Nestor - Facebook",
                "url": "https://www.facebook.com/groups/example/posts/1",
                "content": "A social post about the ring",
            },
            {
                "title": "Protected PDF page",
                "url": "https://archiv.ub.uni-heidelberg.de/propylaeumdok/4408/1/file.pdf",
                "content": "This site is protected by Anubis",
            },
            {
                "title": "Ashmolean object record",
                "url": "https://collections.ashmolean.org/object/478083",
                "content": "Gold signet ring in the Ashmolean Museum collection.",
            },
        ]
    }

    filtered_core = searcher._filter_search_payload(payload, core_query)
    core_urls = [item["url"] for item in filtered_core["results"]]
    assert core_urls == ["https://collections.ashmolean.org/object/478083"], core_urls
    assert filtered_core["dropped_results"] == 2, filtered_core

    filtered_reception = searcher._filter_search_payload(payload, reception_query)
    reception_urls = [item["url"] for item in filtered_reception["results"]]
    assert "https://www.facebook.com/groups/example/posts/1" in reception_urls, reception_urls
    assert "https://archiv.ub.uni-heidelberg.de/propylaeumdok/4408/1/file.pdf" not in reception_urls, reception_urls

    junk_payload = {
        "results": [
            {
                "title": "Hosted shell",
                "url": "https://www.academia.edu/123",
                "content": "Key takeaways sparkles AI",
            },
            {
                "title": "Scribd shell",
                "url": "https://www.scribd.com/document/1/test",
                "content": "Uploaded by ... Share this document ... Get our free apps",
            },
        ]
    }
    emptied = searcher._filter_search_payload(junk_payload, core_query)
    assert emptied["results"] == [], emptied
    assert emptied["dropped_results"] == 2, emptied

    empty_payload = {"results": [{"title": "", "url": "https://example.com", "content": ""}]}
    filtered_empty = searcher._filter_search_payload(empty_payload, core_query)
    assert filtered_empty["results"] == [], filtered_empty
    assert filtered_empty["dropped_results"] == 1, filtered_empty

    evidence_package = {
        "sources": [
            {
                "local_ref": "s1",
                "url": "https://www.academia.edu/83658257/test",
                "title": "Academia entry",
                "source_type": "paper",
            },
            {
                "local_ref": "s2",
                "url": "https://collections.ashmolean.org/object/478083",
                "title": "Ashmolean object record",
                "source_type": "other",
            },
        ],
        "documents": [
            {"local_ref": "d1", "document_summary": "Hosted summary", "source_ref": "s1"},
            {"local_ref": "d2", "document_summary": "Museum record", "source_ref": "s2"},
        ],
        "statements": [
            {
                "local_ref": "st1",
                "text": "A detailed authenticity claim derived from key takeaways.",
                "document_ref": "d1",
                "source_ref": "s1",
                "limitations": ["Based on paper abstract and platform-generated key takeaways."],
                "confidence": "medium",
            },
            {
                "local_ref": "st2",
                "text": "The ring is in the Ashmolean Museum.",
                "document_ref": "d2",
                "source_ref": "s2",
                "limitations": [],
                "confidence": "high",
            },
        ],
        "evidence": [
            {
                "local_ref": "e1",
                "text": "A hosted-platform summary quote.",
                "document_ref": "d1",
                "source_ref": "s1",
                "limitations": ["Full paper text not visible; only abstract and AI summary accessible."],
                "confidence": "medium",
            },
            {
                "local_ref": "e2",
                "text": "Signet ring; Ring of Nestor. Ashmolean Museum.",
                "document_ref": "d2",
                "source_ref": "s2",
                "limitations": [],
                "confidence": "high",
            },
        ],
        "conflicts": [
            {"local_ref": "x1", "description": "conflict", "evidence_refs": ["e1", "e2"]},
        ],
    }
    sanitized = searcher._sanitize_evidence_package(evidence_package, core_query)
    assert [item["local_ref"] for item in sanitized["sources"]] == ["s2"], sanitized
    assert [item["local_ref"] for item in sanitized["documents"]] == ["d2"], sanitized
    assert [item["local_ref"] for item in sanitized["statements"]] == ["st2"], sanitized
    assert [item["local_ref"] for item in sanitized["evidence"]] == ["e2"], sanitized
    assert sanitized["conflicts"] == [], sanitized

    public_discourse_package = {
        "sources": [
            {
                "local_ref": "s1",
                "url": "https://www.facebook.com/groups/example/posts/1",
                "title": "Public discussion",
                "source_type": "other",
            },
        ],
        "documents": [{"local_ref": "d1", "document_summary": "Post", "source_ref": "s1"}],
        "statements": [
            {
                "local_ref": "st1",
                "text": "A public social-media post circulated a simplified description of the ring.",
                "document_ref": "d1",
                "source_ref": "s1",
                "limitations": ["Public post."],
                "confidence": "low",
            },
        ],
        "evidence": [],
        "conflicts": [],
    }
    kept_public = searcher._sanitize_evidence_package(public_discourse_package, reception_query)
    assert [item["local_ref"] for item in kept_public["statements"]] == ["st1"], kept_public

    long_query = (
        'Resolve conflict: There is an apparent tension between Evans\'s framing of the Ring of Nestor '
        'within a "sepulchral treasure of gold signet-rings and bead-seals from Thisbe, Boeotia" in his '
        '1925 study and his explicit statement in 1936 that the Ring of Nestor was found by a peasant in '
        'the larger beehive tomb at Pylos before German excavation. The visible materials do not clarify '
        'whether the ring belongs to a Thisbe assemblage or is a separate find from Pylos, nor how these '
        'descriptions are reconciled. -site:wikipedia.org -site:en.wikipedia.org'
    )
    compact = searcher._compact_search_query(long_query)
    assert len(compact) <= 380, len(compact)
    assert '"sepulchral treasure of gold signet-rings and bead-seals from Thisbe, Boeotia"' in compact, compact
    assert "-site:wikipedia.org" in compact and "-site:en.wikipedia.org" in compact, compact

    print("ALL SEARCHER FILTER CHECKS PASSED")


if __name__ == "__main__":
    main()
