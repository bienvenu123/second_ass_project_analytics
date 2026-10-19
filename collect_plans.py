"""Collect the required PostgreSQL EXPLAIN ANALYZE and Neo4j PROFILE evidence."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".codex_deps")))
from local_config import load_local_env
from query_catalog import CYPHER, SQL, SQL_Q7_BASELINE, SQL_Q7_IMPROVED
from run_comparisons import case_parameters


def neo_plan(node):
    return {
        "operator": node.get("operatorType"),
        "identifiers": node.get("identifiers", []),
        "arguments": node.get("arguments", {}),
        "children": [neo_plan(child) for child in node.get("children", [])],
    }


def main():
    load_local_env()
    import psycopg2
    from neo4j import GraphDatabase, Query
    if not os.getenv("PG_DSN"):
        raise SystemExit("Set PG_DSN locally before collecting plans")
    pg = psycopg2.connect(os.environ["PG_DSN"])
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    plans = []
    cases = [("Q2", None, None), ("Q4", "B", 10), ("Q7 improved", "B", 6), ("Q7 baseline", "B", 6)]
    try:
        for label, name, depth in cases:
            q = label.split()[0]
            params = case_parameters(q, name, depth)
            statement = SQL[q]
            if label == "Q7 baseline":
                statement = SQL_Q7_BASELINE
            if label == "Q7 improved":
                statement = SQL_Q7_IMPROVED
            try:
                with pg.cursor() as cur:
                    # Plan collection is outside the timed benchmark; allow the
                    # documented long-running Q7 variants to finish when possible.
                    cur.execute("SET statement_timeout = 180000")
                    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params)
                    plan = cur.fetchone()[0]
                pg.commit()
                plans.append({"engine": "postgresql", "case": label, "plan": plan})
            except Exception as exc:
                pg.rollback()
                plans.append({"engine": "postgresql", "case": label, "error": f"{type(exc).__name__}: {exc}"})
        with driver.session(database="neo4j") as session:
            for q, name, depth in [("Q2", None, None), ("Q4", "B", 10), ("Q7", "B", 6)]:
                params = case_parameters(q, name, depth)
                statement = CYPHER[q]
                if q == "Q7":
                    statement = statement.replace("[:TRANSFER*1..6]", f"[:TRANSFER*1..{depth}]")
                try:
                    result = session.run(Query("PROFILE " + statement, timeout=240), **params)
                    summary = result.consume()
                    prof = summary.profile
                    plans.append({"engine": "neo4j", "case": q, "set": name, "depth": depth,
                                  "profile": neo_plan(prof), "db_hits": getattr(prof, "db_hits", None),
                                  "records": getattr(prof, "records", None),
                                  "elapsed_time_ms": summary.result_available_after + summary.result_consumed_after})
                except Exception as exc:
                    plans.append({"engine": "neo4j", "case": q, "set": name, "depth": depth,
                                  "error": f"{type(exc).__name__}: {exc}"})
    finally:
        pg.close()
        driver.close()
    out = Path("results/plans.json")
    out.write_text(json.dumps(plans, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved {out}; entries={len(plans)}")


if __name__ == "__main__":
    main()

