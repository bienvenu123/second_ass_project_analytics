"""Multiprocess concurrency experiment for Q4 depth 10 and Q7 bound 6."""
import json
import math
import multiprocessing as mp
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(".codex_deps")))
from local_config import load_local_env
from query_catalog import SQL, CYPHER
from run_comparisons import SETS, case_parameters, normalize

TZ = ZoneInfo("Africa/Johannesburg")


def worker(engine, workload, client_id, repetition, barrier, shared_start, qout):
    load_local_env()
    import psycopg2
    from neo4j import GraphDatabase, Query
    q = workload
    depth = 10 if q == "Q4" else 6
    if engine == "postgresql":
        conn = psycopg2.connect(os.environ["PG_DSN"])
    else:
        conn = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    session = conn.session(database="neo4j") if engine == "neo4j" else None
    def execute(set_name):
        params = case_parameters(q, set_name, depth)
        if engine == "postgresql":
            try:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout=60000")
                    cur.execute(SQL[q], params)
                    rows = cur.fetchall()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            if q == "Q7" and rows == [(None,)]:
                rows = []
        else:
            rows = [tuple(r.values()) for r in session.run(Query(CYPHER[q], timeout=60), **params)]
        return rows, params
    try:
        warmup_errors=[]
        for set_name in "ABC":
            try:
                execute(set_name)
            except Exception as exc:
                warmup_errors.append({"set":set_name,"error":f"{type(exc).__name__}: {exc}"})
        barrier.wait()
        while shared_start.value == 0:
            time.sleep(0.001)
        start = shared_start.value
        deadline = start + 15.0
        seq = 0
        while time.perf_counter() < deadline:
            seq += 1
            for set_name in "ABC":
                params = case_parameters(q, set_name, depth)
                entry = {"engine":engine,"workload":q,"client":client_id,"repetition":repetition,"set":set_name,
                         "sequence":seq,"parameters":params,
                         "cat_start":datetime.now(TZ).isoformat()}
                tick=time.perf_counter()
                try:
                    rows,_=execute(set_name)
                    entry.update(status="completed",duration_seconds=time.perf_counter()-tick,
                                 row_count=len(rows),rows=[list(r) for r in rows])
                except Exception as exc:
                    detail = f"{type(exc).__name__}: {exc}"
                    timed_out = "timeout" in detail.lower() or "canceling statement" in detail.lower()
                    entry.update(status="timeout" if timed_out else "error",
                                 duration_seconds=time.perf_counter()-tick,
                                 error=detail)
                qout.put(entry)
        qout.put({"engine":engine,"workload":q,"client":client_id,"repetition":repetition,"status":"client_done",
                  "finished_at":time.perf_counter(),"warmup_errors":warmup_errors})
    except Exception as exc:
        qout.put({"engine":engine,"workload":q,"client":client_id,"repetition":repetition,"status":"client_error",
                  "error":f"{type(exc).__name__}: {exc}"})
    finally:
        if session is not None:
            session.close()
        conn.close()


def expected_lookup():
    path=Path("results/correctness_61.json")
    if not path.exists():
        raise SystemExit("Run run_comparisons.py first; results/correctness_61.json is required for correctness checks")
    data=json.loads(path.read_text(encoding="utf-8"))
    return {(x["query"],x["set"],x["depth"]): normalize(x["postgres_rows"]) for x in data}


def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--engine",choices=("postgresql","neo4j"),required=True)
    args=ap.parse_args()
    load_local_env()
    expected=expected_lookup()
    summary_path=Path(f"results/concurrency_{args.engine}_summary.jsonl")
    existing=set()
    if summary_path.exists():
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                old=json.loads(line)
                existing.add((old["workload"],old["clients"],old["repetition"]))
    ctx=mp.get_context("spawn")
    raw=[]
    for workload in ("Q4","Q7"):
        for clients in (1,4,8,16):
            for rep in (1,2,3):
                if (workload,clients,rep) in existing:
                    print(f"Skipping already recorded {args.engine} {workload}/{clients} repetition {rep}",flush=True)
                    continue
                barrier=ctx.Barrier(clients+1)
                shared_start=ctx.Value("d",0.0)
                qout=ctx.Queue()
                procs=[ctx.Process(target=worker,args=(args.engine,workload,i,rep,barrier,shared_start,qout)) for i in range(clients)]
                for p in procs: p.start()
                try:
                    barrier.wait(timeout=600)
                except Exception as exc:
                    barrier.abort()
                    for p in procs: p.join(timeout=5)
                    raise RuntimeError(f"Clients failed to warm up for {workload}/{clients}: {exc}") from exc
                shared_start.value=time.perf_counter()
                done=0
                run_recs=[]
                done_times=[]
                warmup_failures=0
                while done<clients:
                    entry=qout.get()
                    if entry["status"] in ("client_done","client_error"):
                        done+=1
                        warmup_failures+=len(entry.get("warmup_errors",[]))
                        if entry.get("finished_at"):
                            done_times.append(entry["finished_at"])
                    else:
                        run_recs.append(entry)
                        if entry["status"]=="completed":
                            exp=expected.get((workload,entry["set"],10 if workload=="Q4" else 6))
                            entry["correct"]=(normalize(entry["rows"])==exp)
                        else:
                            entry["correct"]=False
                        raw.append(entry)
                for p in procs:
                    p.join()
                failures=[p.exitcode for p in procs if p.exitcode]
                if failures: print(f"worker exits {failures}",flush=True)
                measured=[r for r in run_recs if r.get("duration_seconds") is not None]
                success=[r["duration_seconds"] for r in measured if r["status"]=="completed" and r.get("correct")]
                elapsed=max(0.001,max(done_times or [time.perf_counter()])-shared_start.value)
                p95=sorted(success)[math.ceil(.95*len(success))-1] if success else None
                summary={"engine":args.engine,"workload":workload,"clients":clients,"repetition":rep,
                         "correct_completions":len(success),"elapsed_seconds":elapsed,
                         "throughput_per_second":len(success)/elapsed if success else 0,
                         "median_latency_seconds":statistics.median(success) if success else None,
                         "p95_latency_seconds":p95,
                         "warmup_failures":warmup_failures,
                         "errors":sum(r["status"]=="error" for r in measured),
                         "timeouts":sum(r["status"]=="timeout" for r in measured),
                         "incorrect":sum(r["status"]=="completed" and not r.get("correct") for r in measured)}
                Path("results").mkdir(exist_ok=True)
                with Path(f"results/concurrency_{args.engine}_requests.jsonl").open("a",encoding="utf-8") as f:
                    for r in run_recs: f.write(json.dumps(r,default=str)+"\n")
                with summary_path.open("a",encoding="utf-8") as f:
                    f.write(json.dumps(summary)+"\n")
                print(json.dumps(summary),flush=True)
    print(f"Saved concurrency results for {args.engine}")


if __name__=="__main__":
    main()
