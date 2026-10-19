"""Independently recount captured CSV rows and transfer audit totals."""
import csv
import json
from pathlib import Path

import mobile_money_generator as g


def main():
    root = Path("data")
    audit = json.loads((root / "capture_audit.json").read_text(encoding="utf-8"))
    report = {"counts": {}, "roles": {}, "transfers": {"count": 0, "sum_amount_rwf": 0,
              "earliest_occurred_at": None, "latest_occurred_at": None}}
    for name in ("customers", "accounts", "devices", "account_devices", "transfers"):
        with (root / f"{name}.csv").open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != g.FIELDS[name]:
                raise ValueError(f"Unexpected {name} CSV header: {reader.fieldnames}")
            count = 0
            for row in reader:
                count += 1
                if name == "accounts":
                    role = row["role"]
                    report["roles"][role] = report["roles"].get(role, 0) + 1
                if name == "transfers":
                    ts, amt = int(row["occurred_at"]), int(row["amount_rwf"])
                    t = report["transfers"]
                    t["count"] += 1
                    t["sum_amount_rwf"] += amt
                    t["earliest_occurred_at"] = ts if t["earliest_occurred_at"] is None else min(ts, t["earliest_occurred_at"])
                    t["latest_occurred_at"] = ts if t["latest_occurred_at"] is None else max(ts, t["latest_occurred_at"])
        report["counts"][name] = count
        expected = g.dataset_info()["expected_counts"][name]
        if count != expected or count != audit["streams"][name]["written_rows"]:
            raise ValueError(f"{name} count mismatch: recounted {count}, expected {expected}")
        print(f"{name}: verified {count:,}", flush=True)
    expected_roles = {"person": 240000, "merchant": 6000, "agent": 2000}
    if report["roles"] != expected_roles:
        raise ValueError(f"Account roles mismatch: {report['roles']}")
    source_transfer_audit = audit["transfers"]
    if report["transfers"] != source_transfer_audit:
        raise ValueError(f"Transfer audit mismatch: CSV={report['transfers']}, capture={source_transfer_audit}")
    print(json.dumps({"status": "PASS", **report}, indent=2))
    Path("results").mkdir(exist_ok=True)
    Path("results/capture_verification.json").write_text(json.dumps({"status": "PASS", **report}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
