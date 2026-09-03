#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 4 ]]; then
    echo "Usage: $0 <version> [benchmark_name] [agency] [article_name]" >&2
    exit 2
fi

version="$1"
benchmark_name="${2:-2025_Mar_Nov}"
agency="${3:-GraphResearcher}"
article_name="${4:-Ring_of_Nestor}"

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wlc_root="$(cd "$project_root/../Wiki_Live_Challenge" && pwd)"
project_python="$project_root/.venv/bin/python"
report_md="$project_root/outputs/$version/report.md"
wlc_md_dir="$wlc_root/data/$benchmark_name/test_data/$agency/md_data"
wlc_json_dir="$wlc_root/data/$benchmark_name/test_data/$agency/json_data"
bench_out="$project_root/outputs/$version/benchmark"

if [[ ! -x "$project_python" ]]; then
    echo "Project Python not found or not executable: $project_python" >&2
    exit 1
fi

if [[ ! -f "$report_md" ]]; then
    echo "Report not found: $report_md" >&2
    exit 1
fi

mkdir -p "$bench_out"

# 1. Copy report.md to WLC-bench data directory.
echo "=== Step 1: Copy report.md to Wiki_Live_Challenge ==="
mkdir -p "$wlc_md_dir"
cp "$report_md" "$wlc_md_dir/$article_name.md"
echo "Copied to $wlc_md_dir/$article_name.md"

# 2. Generate JSON (statement extraction + citation fetch).
echo
echo "=== Step 2: Generate JSON ==="
(
    cd "$wlc_root"
    "$project_python" scripts/generate_json.py \
        -i "data/$benchmark_name/test_data/$agency/md_data/$article_name.md" \
        -o "data/$benchmark_name/test_data/$agency/json_data/$article_name.json" \
        --steps extract,fetch 2>&1 | tee "$bench_out/preprocess.log"
)

# 3. Run full evaluation (writing + verifiability + citation).
echo
echo "=== Step 3: Run evaluation ==="
mkdir -p "$wlc_root/results/$benchmark_name/$agency"
(
    cd "$wlc_root"
    "$project_python" scripts/run_evaluation.py all \
        --benchmark "$benchmark_name" \
        --agency "$agency" \
        -o "results/$benchmark_name/$agency" 2>&1 | tee "$bench_out/benchmark_run.log"
)

# 4. Copy results back.
echo
echo "=== Step 4: Copy results ==="
wlc_results="$wlc_root/results/$benchmark_name/$agency"
if [[ -d "$wlc_results" ]]; then
    cp -R "$wlc_results/." "$bench_out/"
    echo "Results copied to $bench_out"
else
    echo "No results found at $wlc_results"
fi

# 5. Also copy json_data and md_data for reference.
mkdir -p "$bench_out/json_data" "$bench_out/md_data"
if [[ -f "$wlc_json_dir/$article_name.json" ]]; then
    cp "$wlc_json_dir/$article_name.json" "$bench_out/json_data/"
fi
if [[ -f "$wlc_md_dir/$article_name.md" ]]; then
    cp "$wlc_md_dir/$article_name.md" "$bench_out/md_data/"
fi

echo
echo "=== Benchmark complete ==="
echo "Results in: $bench_out"
