"""Plot completed benchmark and concurrency result files into report-ready PNGs."""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(".codex_deps")))

import matplotlib.pyplot as plt

OUT = Path("results")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def benchmark_chart():
    files = sorted(OUT.glob("benchmark_*.jsonl"))
    if not files:
        print("No benchmark JSONL files yet; skipped benchmark chart")
        return
    grouped = defaultdict(list)
    for path in files:
        for row in read_jsonl(path):
            if row.get("run_type") == "measured" and row.get("status") == "completed":
                label = f"{row['engine']} Q7 {row['q7_version']}" if row["case"] == "Q7" else row["engine"]
                case_key = (row["case"], row.get("set") or "", row.get("depth") or "")
                grouped[(case_key, label)].append(row["duration_seconds"])
    cases = []
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
        if q == "Q2":
            cases.append((q, "", ""))
        elif q == "Q4":
            cases.extend((q, s, d) for s in ("B", "E") for d in (4, 6, 8, 10))
        elif q == "Q7":
            cases.extend((q, s, d) for s in ("B", "E") for d in (4, 6))
        else:
            cases.extend((q, s, "") for s in ("B", "E"))
    labels = sorted({key[1] for key in grouped})
    tick_labels = ["-".join(str(v) for v in case if v != "") for case in cases]
    fig, ax = plt.subplots(figsize=(17, 7))
    for label in labels:
        xs, ys = [], []
        for i, case_key in enumerate(cases):
            vals = grouped.get((case_key, label))
            if vals:
                xs.append(i)
                ys.append(statistics.median(vals))
        if xs:
            ax.plot(xs, ys, marker="o", label=label)
    ax.set_xticks(range(len(cases)), tick_labels, rotation=45, ha="right")
    ax.set_ylabel("Median measured latency (seconds, log scale)")
    ax.set_yscale("log")
    ax.set_title("Median latency by benchmark case (completed measured runs)")
    ax.grid(True, alpha=.3)
    ax.axhline(60, color="black", linestyle="--", linewidth=1, alpha=.45, label="60 s measured timeout")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "benchmark_latency.png", dpi=180)
    plt.close(fig)


def concurrency_chart():
    files = sorted(OUT.glob("concurrency_*_summary.jsonl"))
    if not files:
        print("No concurrency summaries yet; skipped concurrency chart")
        return
    grouped = defaultdict(lambda: defaultdict(list))
    for path in files:
        for row in read_jsonl(path):
            grouped[(row["engine"], row["workload"])][row["clients"]].append(row["throughput_per_second"])
    fig, ax = plt.subplots(figsize=(9, 6))
    for (engine, workload), points in sorted(grouped.items()):
        xs = sorted(points)
        ys = [statistics.median(points[x]) for x in xs]
        ax.plot(xs, ys, marker="o", label=f"{engine} {workload}")
    ax.set_xlabel("Concurrent clients")
    ax.set_ylabel("Median correct completions per second")
    ax.set_title("Concurrent query throughput")
    ax.grid(True, alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "concurrency_throughput.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 6))
    for (engine, workload), points in sorted(grouped.items()):
        xs = sorted(points)
        vals = {}
        for path in files:
            if f"{engine}" not in path.name:
                continue
            for row in read_jsonl(path):
                if row["workload"] == workload:
                    vals.setdefault(row["clients"], []).append(row.get("p95_latency_seconds"))
        ys = [statistics.median(v for v in vals.get(x, []) if v is not None) if any(v is not None for v in vals.get(x, [])) else float("nan") for x in xs]
        ax.plot(xs, ys, marker="o", label=f"{engine} {workload}")
    ax.set_xlabel("Concurrent clients")
    ax.set_ylabel("Median repetition p95 latency (seconds)")
    ax.set_title("Concurrent query p95 latency")
    ax.grid(True, alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "concurrency_p95.png", dpi=180)
    plt.close(fig)


def data_charts():
    path = OUT / "correctness_61.json"
    if not path.exists():
        return
    rows = read_jsonl(path) if path.suffix == ".jsonl" else json.loads(path.read_text(encoding="utf-8"))
    q2 = next((x for x in rows if x["query"] == "Q2"), None)
    if q2 and q2.get("postgres_rows"):
        dates = [str(r[0]) for r in q2["postgres_rows"]]
        counts = [int(r[1]) for r in q2["postgres_rows"]]
        amounts = [int(r[2]) for r in q2["postgres_rows"]]
        fig, left = plt.subplots(figsize=(12, 6))
        x = list(range(len(dates)))
        left.bar(x, counts, color="#2878B5", label="Transfers")
        left.set_ylabel("Transfer count")
        right = left.twinx()
        right.plot(x, amounts, color="#E07A1F", marker="o", label="Total value")
        right.set_ylabel("Total amount (RWF)")
        left.set_xticks(x, dates, rotation=45, ha="right")
        left.set_title("September daily mobile money activity (Africa/Kigali)")
        fig.tight_layout()
        fig.savefig(OUT / "q2_daily_activity.png", dpi=180)
        plt.close(fig)

    q4 = [r for r in rows if r["query"] == "Q4" and r.get("postgres_rows") is not None]
    if q4:
        points = {}
        for r in q4:
            points.setdefault((r["set"], r["depth"]), 0)
            points[(r["set"], r["depth"])] += sum(int(v[1]) for v in r["postgres_rows"])
        fig, ax = plt.subplots(figsize=(9, 6))
        for name in sorted({k[0] for k in points}):
            xs = sorted(k[1] for k in points if k[0] == name)
            ax.plot(xs, [points[(name, d)] for d in xs], marker="o", label=f"Set {name}")
        ax.set_xlabel("Maximum links")
        ax.set_ylabel("Distinct connected accounts")
        ax.set_title("Ownership/device network reach by depth")
        ax.grid(True, alpha=.3)
        ax.legend(ncol=3)
        fig.tight_layout()
        fig.savefig(OUT / "q4_reach_by_depth.png", dpi=180)
        plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    benchmark_chart()
    concurrency_chart()
    data_charts()
