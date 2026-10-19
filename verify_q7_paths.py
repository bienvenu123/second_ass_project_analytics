"""Validate one supporting person-only transfer route for each reachable Q7 case."""
import json
import os
import sys
from pathlib import Path

from local_config import load_local_env
from query_catalog import CYPHER_Q7_PATH
from run_comparisons import SETS, case_parameters


def check_path(cur, accounts, transfer_ids, start, destination, bound):
    if len(accounts) != len(transfer_ids) + 1 or not transfer_ids or len(transfer_ids) > bound:
        return False, "path lengths violate bound"
    if accounts[0] != start or accounts[-1] != destination:
        return False, "wrong endpoints"
    cur.execute("SELECT transfer_id,sender_id,receiver_id FROM transfers WHERE transfer_id=ANY(%s)", (transfer_ids,))
    edges = {int(tid):(int(s),int(r)) for tid,s,r in cur.fetchall()}
    if len(edges) != len(transfer_ids):
        return False, "missing or duplicate transfer IDs"
    cur.execute("SELECT account_id FROM accounts WHERE account_id=ANY(%s) AND role='person'", (accounts,))
    people = {int(row[0]) for row in cur.fetchall()}
    if people != set(accounts):
        return False, "path contains a non-person or missing account"
    for i, tid in enumerate(transfer_ids):
        if edges.get(tid) != (accounts[i], accounts[i+1]):
            return False, f"transfer {tid} has wrong direction/endpoints"
    return True, "all nodes/edges verified"


def main():
    load_local_env()
    import psycopg2
    from neo4j import GraphDatabase, Query
    pg = psycopg2.connect(os.environ["PG_DSN"])
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    correctness = json.loads(Path("results/correctness_61.json").read_text(encoding="utf-8"))
    expected = {(x["query"],x["set"],x["depth"]):x["postgres_rows"] for x in correctness if x["query"]=="Q7"}
    output=[]
    try:
        with driver.session(database="neo4j") as neo, pg.cursor() as cur:
            for name in SETS:
                for depth in (4,6):
                    params=case_parameters("Q7",name,depth)
                    want=expected[("Q7",name,depth)]
                    expected_length=int(want[0][0]) if want else None
                    entry={"set":name,"depth":depth,"expected_length":expected_length,"postgres_validation":None,"neo4j":None}
                    if expected_length is None:
                        output.append(entry); continue
                    statement=CYPHER_Q7_PATH.replace("[:TRANSFER*1..6]",f"[:TRANSFER*1..{depth}]")
                    try:
                        recs=list(neo.run(Query(statement, timeout=60), **params))
                    except Exception as exc:
                        entry["neo4j_error"]=f"{type(exc).__name__}: {exc}"
                        output.append(entry)
                        continue
                    if recs:
                        r=recs[0]
                        accounts=list(map(int,r["accounts"])); tids=list(map(int,r["transfer_ids"]))
                        valid,msg=check_path(cur,accounts,tids,params["account"],params["destination"],depth)
                        entry["neo4j"]={"length":int(r["min_length"]),"accounts":accounts,"transfer_ids":tids,"valid":valid,"check":msg}
                        entry["postgres_validation"]={"valid":valid,"check":"Transfer IDs, direction, endpoints, account roles, and route length checked against PostgreSQL"}
                        entry["neo4j"]["matches_minimum"]=(entry["neo4j"]["length"]==expected_length)
                    output.append(entry)
                    print(f"{name} depth {depth}: path={entry['neo4j'] is not None} PG-edge-check={entry['postgres_validation'] is not None}",flush=True)
        pg.commit()
    finally:
        pg.close();driver.close()
    target=Path("results/q7_path_verification.json")
    target.write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    fails=[x for x in output if x["expected_length"] is not None and
           (x.get("neo4j") is None or not x["neo4j"]["valid"] or not x["neo4j"]["matches_minimum"])]
    print(f"Saved {target}; paths checked={sum(x.get('neo4j') is not None for x in output)}; failures={len(fails)}")
    if fails: raise SystemExit(1)

if __name__=="__main__": main()
