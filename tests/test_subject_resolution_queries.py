"""Checks for conservative subject-resolution query seeding on named-subject tasks."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import _ensure_subject_query_coverage, _subject_resolution_query  # noqa: E402


OBJECTIVES = [
    {
        "objective_key": "identity-scope",
        "description": "Establish the identity, discovery, and basic description of the artefact known as the 'Ring of Nestor'.",
        "text": "Establish the identity, discovery, and basic description of the artefact known as the 'Ring of Nestor'.",
        "requirement": "must",
        "acceptance_criteria": [
            "Clarify what the 'Ring of Nestor' is.",
            "Provide reliable information on discovery circumstances.",
        ],
    },
    {
        "objective_key": "iconography-interpretation",
        "description": "Describe and analyze the iconography and scholarly interpretations of the Ring of Nestor.",
        "text": "Describe and analyze the iconography and scholarly interpretations of the Ring of Nestor.",
        "requirement": "must",
        "acceptance_criteria": [
            "Summarize the imagery depicted on the Ring of Nestor.",
        ],
    },
]

USER_REQUEST = (
    'Write an article about the "Ring of Nestor", including its identity, discovery, '
    "and iconography."
)
EXPECTED_QUERY = '"Ring of Nestor" identity scope provenance discovery authenticity'


def main():
    planner_queries = [
        {
            "text": '"Ring of Nestor" gold ring Pylos Mycenaean discovery physical description',
            "importance": "core",
            "objective_keys": ["identity-scope"],
            "acceptance_criteria": ["Provide reliable information on discovery circumstances."],
        },
        {
            "text": '"Ring of Nestor" iconography scene description scholarly interpretation',
            "importance": "core",
            "objective_keys": ["iconography-interpretation"],
            "acceptance_criteria": ["Summarize the imagery depicted on the Ring of Nestor."],
        },
    ]

    query = _subject_resolution_query(USER_REQUEST, "English", OBJECTIVES, planner_queries)
    assert query is not None, "Expected a conservative subject-resolution query to be added"
    assert query["text"] == EXPECTED_QUERY, query

    covered = _ensure_subject_query_coverage(USER_REQUEST, "English", OBJECTIVES, planner_queries)
    texts = [item["text"] for item in covered]
    assert EXPECTED_QUERY in texts, texts

    exact_duplicate = _subject_resolution_query(
        USER_REQUEST,
        "English",
        OBJECTIVES,
        [{"text": EXPECTED_QUERY, "objective_keys": ["identity-scope"]}],
    )
    assert exact_duplicate is None, "Exact identity query should not be duplicated"

    print("ALL SUBJECT-RESOLUTION QUERY CHECKS PASSED")


if __name__ == "__main__":
    main()
