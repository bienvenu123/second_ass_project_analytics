"""Aggregate raw benchmark records without folding timeouts into latencies."""
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

OUT = Path("results")


def main():
    groups = defaultdict(list)
    for path in sorted(OUT.glob("benchmark_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("run_type") != "measured":
                continue
            key = (row["engine"], row.get("q7_version") or "standard", row["case"], row.get("set") or "all", row.get("depth") or "")
            groups[key].append(row)
    out = []
    for key, records in sorted(groups.items()):
        completed = [r["duration_seconds"] * 1000 for r in records if r["status"] == "completed"]
        out.append({"engine": key[0], "version": key[1], "query": key[2], "set": key[3], "depth": key[4],
                    "measured": len(records), "completed": len(completed),
                    "timeouts": sum(r["status"] == "timeout" for r in records),
                    "errors": sum(r["status"] == "error" for r in records),
                    "median_ms": statistics.median(completed) if completed else None,
                    "minimum_ms": min(completed) if completed else None,
                    "maximum_ms": max(completed) if completed else None})
    (OUT / "benchmark_summary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    with (OUT / "benchmark_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out[0].keys() if out else [])
        writer.writeheader(); writer.writerows(out)
    print(f"Summarized {len(out)} case groups")


if __name__ == "__main__":
    main()
