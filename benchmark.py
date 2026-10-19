"""Fixed selection benchmark: 21 cases, 3 warmups, 5 measured runs each."""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(".codex_deps")))
import psycopg2
from neo4j import GraphDatabase
import query_catalog as qc
from local_config import load_local_env
from run_comparisons import SETS, case_parameters, normalize

TZ = ZoneInfo("Africa/Kigali")


def cases():
    out = [("Q1", s, None) for s in ("B", "E")]
    out += [("Q2", None, None)]
    out += [("Q3", s, None) for s in ("B", "E")]
    out += [("Q4", s, d) for s in ("B", "E") for d in (4, 6, 8, 10)]
    out += [("Q5", s, None) for s in ("B", "E")]
    out += [("Q6", s, None) for s in ("B", "E")]
    out += [("Q7", s, d) for s in ("B", "E") for d in (4, 6)]
    assert len(out) == 21
    return out


def pg_rows(conn, q, params, timeout):
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (int(timeout * 1000),))
            cur.execute(qc.SQL[q], params)
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if q == "Q7" and rows == [(None,)]:
        return []
    return rows


def neo_rows(session, q, params, timeout):
    from neo4j import Query
    statement = qc.CYPHER[q]
    if q == "Q7":
        statement = statement.replace("[:TRANSFER*1..6]", f"[:TRANSFER*1..{params['depth']}]")
    # `timeout` passed as a keyword to Session.run becomes a Cypher parameter.
    # Wrap the statement in Query so the driver applies a transaction timeout.
    return [tuple(r.values()) for r in session.run(Query(statement, timeout=timeout), **params)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("postgresql", "neo4j"), required=True)
    ap.add_argument("--q7-version", choices=("baseline", "improved"), default="improved")
    args = ap.parse_args()
    load_local_env()
    connection = None
    driver = None
    if args.engine == "postgresql":
        if not os.getenv("PG_DSN"):
            raise SystemExit("Set PG_DSN in .env before benchmarking PostgreSQL")
        connection = psycopg2.connect(os.environ["PG_DSN"])
    else:
        driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
        driver.verify_connectivity()
        connection = driver.session(database="neo4j")
    dest = Path("results") / f"benchmark_{args.engine}_{args.q7_version}.jsonl"
    dest.parent.mkdir(exist_ok=True)
    try:
        with dest.open("w", encoding="utf-8") as out:
            for q, name, depth in cases():
                params = case_parameters(q, name, depth)
                statement = qc.SQL[q] if args.engine == "postgresql" else qc.CYPHER[q]
                if q == "Q7" and args.engine == "postgresql" and args.q7_version == "baseline":
                    statement = qc.SQL_Q7_BASELINE
                def execute(timeout):
                    if args.engine == "postgresql":
                        # Use the selected statement, including the retained baseline Q7 variant.
                        old = qc.SQL[q]
                        qc.SQL[q] = statement
                        try:
                            return pg_rows(connection, q, params, timeout)
                        finally:
                            qc.SQL[q] = old
                    return neo_rows(connection, q, params, timeout)
                for run_no in range(1, 4):
                    row = {"case": q, "set": name, "depth": depth, "parameters": params,
                           "engine": args.engine, "run_type": "warmup", "run": run_no,
                           "q7_version": args.q7_version if q == "Q7" else None,
                           "cat_start": datetime.now(TZ).isoformat()}
                    started = time.perf_counter()
                    try:
                        rows = execute(180)
                        row.update(status="completed", duration_seconds=time.perf_counter()-started, row_count=len(rows))
                    except Exception as exc:
                        detail = f"{type(exc).__name__}: {exc}"
                        is_timeout = any(term in detail.lower() for term in ("timeout", "timed out", "time limit", "canceling statement"))
                        row.update(status="timeout" if is_timeout else "error",
                                   error=detail)
                    out.write(json.dumps(row,default=str)+"\n"); out.flush()
                for run_no in range(1, 6):
                    row = {"case": q, "set": name, "depth": depth, "parameters": params,
                           "engine": args.engine, "run_type": "measured", "run": run_no,
                           "q7_version": args.q7_version if q == "Q7" else None,
                           "cat_start": datetime.now(TZ).isoformat()}
                    started = time.perf_counter()
                    try:
                        rows = execute(60)
                        row.update(status="completed", duration_seconds=time.perf_counter()-started, row_count=len(rows))
                    except Exception as exc:
                        detail = f"{type(exc).__name__}: {exc}"
                        is_timeout = any(term in detail.lower() for term in ("timeout", "timed out", "time limit", "canceling statement"))
                        row.update(status="timeout" if is_timeout else "error", error=detail)
                    out.write(json.dumps(row,default=str)+"\n"); out.flush()
                print(f"{args.engine} {q} {name or '-'} {depth or '-'}: measured runs recorded",flush=True)
    finally:
        connection.close()
        if driver is not None:
            driver.close()
    print(f"Saved {dest}")


if __name__ == "__main__":
    main()
