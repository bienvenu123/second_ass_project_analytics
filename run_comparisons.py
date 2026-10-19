"""Run the assignment's 61 SQL/Cypher correctness cases."""
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
from query_catalog import CYPHER, SQL
from local_config import load_local_env

try:
    from neo4j import GraphDatabase
except ImportError as e:
    raise SystemExit("Install the Neo4j Python driver (`python -m pip install neo4j`) before running comparisons") from e

TZ = ZoneInfo("Africa/Kigali")
SETS = {
    "A": (998, 24755, 6), "B": (147228, 186823, 13),
    "C": (206978, 6573, 8), "D": (237998, 21755, 6),
    "E": (144228, 183823, 13), "F": (203978, 3573, 8),
}


def epoch(day, hour=9, minute=45):
    return int(datetime.combine(date(2026, 9, day), time(hour, minute), TZ).timestamp())


def case_parameters(q, name=None, depth=None):
    if q == "Q2":
        return {}
    account, destination, day = SETS[name]
    p = {"account": account}
    if q in ("Q1", "Q5", "Q6"):
        p.update(start=epoch(day), end=epoch(day, 10, 45))
    if q == "Q4":
        p["depth"] = depth
    if q == "Q7":
        p.update(destination=destination, depth=depth)
    return p


def case_list():
    cases = [("Q1", s, None) for s in SETS]
    cases += [("Q2", None, None)]
    cases += [("Q3", s, None) for s in SETS]
    cases += [("Q4", s, d) for s in SETS for d in (4, 6, 8, 10)]
    cases += [("Q5", s, None) for s in SETS]
    cases += [("Q6", s, None) for s in SETS]
    cases += [("Q7", s, d) for s in SETS for d in (4, 6)]
    assert len(cases) == 61
    return cases


def normalize(rows):
    def val(x):
        if hasattr(x, "isoformat"):
            return x.isoformat()
        if isinstance(x, list):
            return tuple(val(i) for i in x)
        if isinstance(x, tuple):
            return tuple(val(i) for i in x)
        return x
    return sorted((tuple(val(x) for x in row) for row in rows), key=repr)


def run_pg(conn, q, params):
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 300000")
            cur.execute(SQL[q], params)
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    # Neo4j yields no record for an unreachable Q7 destination; SQL aggregates one NULL.
    if q == "Q7" and rows == [(None,)]:
        return []
    return rows


def run_neo(session, q, params):
    from neo4j import Query
    statement = CYPHER[q]
    if q == "Q7":
        # Match the requested bound directly; a hard-coded six-edge shortest path
        # can explore a much larger search space for depth-four correctness cases.
        statement = statement.replace("[:TRANSFER*1..6]", f"[:TRANSFER*1..{params['depth']}]")
    timeout = 240 if q == "Q2" else 60 if q == "Q7" else 30
    return [tuple(record.values()) for record in session.run(Query(statement, timeout=timeout), **params)]


def main():
    load_local_env()
    missing = [k for k in ("PG_DSN", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise SystemExit("Set connection environment variables: " + ", ".join(missing))
    pg = psycopg2.connect(os.environ["PG_DSN"])
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    out = []
    try:
        with driver.session(database="neo4j") as neo:
            for q, name, depth in case_list():
                params = case_parameters(q, name, depth)
                entry = {"query": q, "set": name, "depth": depth, "params": params}
                try:
                    left = normalize(run_pg(pg, q, params))
                    entry["postgres_rows"] = left
                except Exception as exc:
                    entry.update(status="POSTGRES_ERROR", error=f"{type(exc).__name__}: {exc}")
                    left = None
                if entry.get("status") != "POSTGRES_ERROR":
                    try:
                        right = normalize(run_neo(neo, q, params))
                        entry["neo4j_rows"] = right
                        entry["status"] = "PASS" if left == right else "MISMATCH"
                    except Exception as exc:
                        entry.update(status="NEO4J_TIMEOUT" if "timeout" in f"{type(exc).__name__} {exc}".lower()
                                     else "NEO4J_ERROR", error=f"{type(exc).__name__}: {exc}")
                out.append(entry)
                print(f"{len(out):02}/61 {q} {name or '-'} {depth or '-'}: {out[-1]['status']}", flush=True)
                target = Path("results")
                target.mkdir(exist_ok=True)
                (target / "correctness_61.json").write_text(
                    json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    finally:
        driver.close()
        pg.close()
    failures = sum(r["status"] != "PASS" for r in out)
    print(f"Completed {len(out)} cases; failures={failures}; results=results/correctness_61.json")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
