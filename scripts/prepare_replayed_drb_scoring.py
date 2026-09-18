"""Prepare Reporter-replay reports for the official DRB scorer."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ITEMS = (1, 17, 19, 31, 34)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    records: list[dict] = []
    report_records: list[dict] = []
    for item in ITEMS:
        task_root = args.run_root / f"drb-{item}"
        input_path = task_root / "inputs" / "query.jsonl"
        replay_report = task_root / "reporter_replays" / f"id-{item}" / "report.md"
        if not input_path.is_file() or not replay_report.is_file():
            raise FileNotFoundError(f"Missing replay input/report for id={item}")
        task_records = [
            json.loads(line)
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        record = next(record for record in task_records if record.get("id") == item)
        records.append(record)
        target = args.output_root / "report" / "GraphResearcher-replay" / f"id-{item}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(replay_report, target)
        report_records.append({
            "id": item,
            "prompt": record["prompt"],
            "article": replay_report.read_text(encoding="utf-8"),
        })

    raw_path = args.output_root / "raw_data" / "GraphResearcher-replay.jsonl"
    query_path = args.output_root / "_evaluation" / "GraphResearcher-replay" / "query.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in report_records),
        encoding="utf-8",
    )
    query_path.write_text(
        "".join(
            json.dumps(
                {key: record[key] for key in ("id", "topic", "language", "prompt") if key in record},
                ensure_ascii=False,
            ) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    print(f"Prepared {len(records)} replay reports under {args.output_root}")


if __name__ == "__main__":
    main()
