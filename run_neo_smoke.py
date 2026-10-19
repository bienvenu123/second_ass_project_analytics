"""Run one loaded-data example for each Cypher question and save full rows."""
import json
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(".codex_deps")))
    from neo4j import GraphDatabase, Query
from local_config import load_local_env
from query_catalog import CYPHER
from run_comparisons import case_parameters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("Q1","Q2","Q3","Q4","Q5","Q6","Q7"), action="append")
    selected = ap.parse_args().only or ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7")
    load_local_env()
    import os
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    out = []
    try:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            for q in selected:
                params = case_parameters(q, "A", 4 if q == "Q4" else 6 if q == "Q7" else None)
                started = time.perf_counter()
                rows = [dict(r) for r in session.run(Query(CYPHER[q], timeout=180), **params)]
                entry = {"query": q, "set": "A", "depth": params.get("depth"), "params": params,
                         "elapsed_seconds": round(time.perf_counter()-started,3), "rows": rows}
                out.append(entry)
                print(f"{q}: {len(rows)} rows in {entry['elapsed_seconds']}s", flush=True)
    finally:
        driver.close()
    Path("results").mkdir(exist_ok=True)
    dest = Path("results/neo4j_smoke.json")
    if dest.exists() and len(selected) < 7:
        previous = json.loads(dest.read_text(encoding="utf-8"))
        merged = {item["query"]: item for item in previous}
        merged.update({item["query"]: item for item in out})
        out = [merged[k] for k in sorted(merged)]
    dest.write_text(json.dumps(out,indent=2,default=str)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
