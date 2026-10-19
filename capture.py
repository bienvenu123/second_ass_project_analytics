"""Stream the fixed teaching data into CSVs and write a capture audit."""
import argparse
import csv
import json
import time
from itertools import islice
from pathlib import Path

import mobile_money_generator as g


def preview(limit=10):
    for stream in ("customers", "accounts", "devices", "account_devices", "transfers"):
        rows = list(islice(getattr(g, f"iter_{stream}")(), limit))
        print(f"\n{stream}: {len(rows)} preview rows")
        for row in rows:
            print(row)


def capture(outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    audit = {"dataset": g.dataset_info(), "streams": {}}
    for stream in ("customers", "accounts", "devices", "account_devices", "transfers"):
        path = outdir / f"{stream}.csv"
        fields = g.FIELDS[stream]
        started = time.perf_counter()
        count = 0
        transfer_sum = 0
        earliest = latest = None
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in getattr(g, f"iter_{stream}")():
                writer.writerow(row)
                count += 1
                if stream == "transfers":
                    ts = row["occurred_at"]
                    earliest = ts if earliest is None else min(earliest, ts)
                    latest = ts if latest is None else max(latest, ts)
                    transfer_sum += row["amount_rwf"]
                    if count % 1_000_000 == 0:
                        print(f"{stream}: {count:,} rows written", flush=True)
        expected = g.dataset_info()["expected_counts"][stream]
        if count != expected:
            raise RuntimeError(f"{stream}: wrote {count:,}, expected {expected:,}")
        audit["streams"][stream] = {
            "consumed_rows": count, "written_rows": count,
            "expected_rows": expected, "elapsed_seconds": round(time.perf_counter() - started, 3),
            "csv_bytes": path.stat().st_size,
        }
        if stream == "transfers":
            audit["transfers"] = {"count": count, "earliest_occurred_at": earliest,
                                   "latest_occurred_at": latest, "sum_amount_rwf": transfer_sum}
        print(f"{stream}: {count:,} rows, {path.stat().st_size:,} bytes, "
              f"{audit['streams'][stream]['elapsed_seconds']:.1f}s", flush=True)
    (outdir / "capture_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"Audit: {outdir / 'capture_audit.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preview", "capture"))
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args()
    preview() if args.action == "preview" else capture(args.out)
