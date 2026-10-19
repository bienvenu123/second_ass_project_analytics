"""Cross-check saved Neo4j smoke results against the source CSV files."""
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Kigali")


def main():
    smoke = {r["query"]: r for r in json.loads(Path("results/neo4j_smoke.json").read_text(encoding="utf-8"))}
    q1 = smoke["Q1"]
    p = q1["params"]
    q1_count = q1_sum = 0
    transfer_rows_scanned = 0
    q2 = defaultdict(lambda: [0, 0])
    wanted = set()
    for q in ("Q5", "Q6"):
        for row in smoke[q]["rows"]:
            if q == "Q5":
                wanted.update(row[k] for k in ("transfer_1", "transfer_2", "transfer_3"))
            else:
                wanted.update(row["transfer_ids"])
    selected = {}
    with Path("data/transfers.csv").open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            transfer_rows_scanned += 1
            tid = int(row["transfer_id"])
            sender, receiver = int(row["sender_id"]), int(row["receiver_id"])
            stamp, amount = int(row["occurred_at"]), int(row["amount_rwf"])
            if sender == p["account"] and p["start"] <= stamp < p["end"]:
                q1_count += 1
                q1_sum += amount
            day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(TZ).date().isoformat()
            q2[day][0] += 1
            q2[day][1] += amount
            if tid in wanted:
                selected[tid] = (sender, receiver, stamp, amount)
    q1_pass = q1["rows"] == [{"transfer_count": q1_count, "total_rwf": q1_sum}]
    expected_q2 = [{"cat_date": d, "transfer_count": n, "total_rwf": total}
                   for d, (n, total) in sorted(q2.items())]
    # JSON's default encoder stores temporal driver values as ISO strings.
    q2_pass = smoke["Q2"]["rows"] == expected_q2

    params = smoke["Q3"]["params"]
    by_device = defaultdict(list)
    with Path("data/account_devices.csv").open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            by_device[int(row["device_id"])].append(
                (int(row["account_id"]), int(row["first_day"]), int(row["last_day"]))
            )
    with Path("data/devices.csv").open("r", encoding="utf-8", newline="") as stream:
        access = {int(r["device_id"]): r["access_type"] for r in csv.DictReader(stream)}
    expected_q3 = set()
    for device, uses in by_device.items():
        mine = [u for u in uses if u[0] == params["account"]]
        others = [u for u in uses if u[0] != params["account"]]
        for a, f1, l1 in mine:
            for b, f2, l2 in others:
                if f1 <= l2 and f2 <= l1:
                    expected_q3.add((b, device, access[device], max(f1, f2), min(l1, l2)))
    got_q3 = {tuple(r[k] for k in ("other_account", "device_id", "access_type", "overlap_start", "overlap_end"))
              for r in smoke["Q3"]["rows"]}
    q3_pass = got_q3 == expected_q3

    def valid_chain(ids, start_account=None, end_account=None, window=None, cycle_seconds=None):
        if not ids or any(tid not in selected for tid in ids):
            return False
        edges = [selected[tid] for tid in ids]
        if any(edges[i][1] != edges[i + 1][0] for i in range(len(edges) - 1)):
            return False
        if start_account is not None and edges[0][0] != start_account:
            return False
        if end_account is not None and edges[-1][1] != end_account:
            return False
        if window and any(not (window[0] <= e[2] < window[1]) for e in edges):
            return False
        if any(edges[i + 1][2] <= edges[i][2] for i in range(len(edges) - 1)):
            return False
        if cycle_seconds is not None and edges[-1][2] - edges[0][2] > cycle_seconds:
            return False
        return all(90 * edges[i][3] <= 100 * edges[i + 1][3] <= 105 * edges[i][3]
                   for i in range(len(edges) - 1))

    q5_ok = all(valid_chain([r["transfer_1"], r["transfer_2"], r["transfer_3"]],
                            start_account=smoke["Q5"]["params"]["account"],
                            end_account=r["final_receiver"],
                            window=(smoke["Q5"]["params"]["start"], smoke["Q5"]["params"]["end"]),
                            cycle_seconds=1200)
                for r in smoke["Q5"]["rows"])
    q6_ok = all(valid_chain(r["transfer_ids"], start_account=smoke["Q6"]["params"]["account"],
                            end_account=smoke["Q6"]["params"]["account"],
                            window=(smoke["Q6"]["params"]["start"], smoke["Q6"]["params"]["end"]),
                            cycle_seconds=1800) and len(r["transfer_ids"]) == r["length"]
                for r in smoke["Q6"]["rows"])
    results = {"Q1_transfer_window": q1_pass, "Q2_daily_totals": q2_pass,
               "Q3_device_overlap": q3_pass, "Q5_returned_chains": q5_ok, "Q6_returned_cycles": q6_ok}
    result = {"status": "PASS" if all(results.values()) else "FAIL", "checks": results,
              "transfer_rows_scanned": transfer_rows_scanned}
    Path("results/query_sample_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
