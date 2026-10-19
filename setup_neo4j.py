"""Add required Neo4j schema objects and verify the imported graph."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".codex_deps")))
from neo4j import GraphDatabase
from local_config import load_local_env


SCHEMA = (
    "CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE",
    "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (n:Account) REQUIRE n.account_id IS UNIQUE",
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (n:Device) REQUIRE n.device_id IS UNIQUE",
    "CREATE RANGE INDEX transfer_occurred_at IF NOT EXISTS FOR ()-[r:TRANSFER]-() ON (r.occurred_at)",
)
COUNTS = {
    "customers": "MATCH (n:Customer) RETURN count(n) AS n",
    "accounts": "MATCH (n:Account) RETURN count(n) AS n",
    "devices": "MATCH (n:Device) RETURN count(n) AS n",
    "owns": "MATCH ()-[r:OWNS]->() RETURN count(r) AS n",
    "used_device": "MATCH ()-[r:USED_DEVICE]->() RETURN count(r) AS n",
    "transfers": "MATCH ()-[r:TRANSFER]->() RETURN count(r) AS n",
}


def folder_bytes(folder):
    folder = Path(folder)
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.exists() else 0


def main():
    load_local_env()
    uri, user, password = (os.getenv(k) for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"))
    if not all((uri, user, password)):
        raise SystemExit("Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD in .env")
    home = Path(os.getenv("NEO4J_HOME", ""))
    if not home.is_dir():
        raise SystemExit("Set NEO4J_HOME in .env to the project DBMS directory")
    audit = json.loads(Path("data/capture_audit.json").read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(uri, auth=(user, password))
    result = {"uri": uri, "database": "neo4j"}
    try:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            for statement in SCHEMA:
                session.run(statement).consume()
            session.run("CALL db.awaitIndexes(300)").consume()
            result["indexes"] = [dict(r) for r in session.run("SHOW INDEXES YIELD name,state,type,entityType,labelsOrTypes,properties RETURN name,state,type,entityType,labelsOrTypes,properties ORDER BY name")]
            result["constraints"] = [dict(r) for r in session.run("SHOW CONSTRAINTS YIELD name,type,entityType,labelsOrTypes,properties RETURN name,type,entityType,labelsOrTypes,properties ORDER BY name")]
            for key, query in COUNTS.items():
                result.setdefault("counts", {})[key] = session.run(query).single()["n"]
            result["roles"] = {r["role"]: r["n"] for r in session.run("MATCH (a:Account) RETURN a.role AS role,count(*) AS n ORDER BY role")}
            result["transfer_audit"] = dict(session.run("MATCH ()-[r:TRANSFER]->() RETURN count(r) AS count,min(r.occurred_at) AS earliest_occurred_at,max(r.occurred_at) AS latest_occurred_at,sum(r.amount_rwf) AS sum_amount_rwf,count(DISTINCT r.transfer_id) AS unique_transfer_ids").single())
            result["accounts_with_wrong_owner_count"] = session.run("MATCH (a:Account) OPTIONAL MATCH (c:Customer)-[r:OWNS]->(a) WITH a,count(r) AS n WHERE n<>1 RETURN count(a) AS n").single()["n"]
    finally:
        driver.close()
    expected_counts = {"customers":228000,"accounts":248000,"devices":228600,
                       "owns":248000,"used_device":285600,"transfers":20003300}
    expected_audit = audit["transfers"]
    if result["counts"] != expected_counts:
        raise RuntimeError(f"Node/relationship count mismatch: {result['counts']}")
    if result["roles"] != {"person":240000,"merchant":6000,"agent":2000}:
        raise RuntimeError(f"Role mismatch: {result['roles']}")
    check_audit = {k: result["transfer_audit"][k] for k in expected_audit}
    if check_audit != expected_audit or result["transfer_audit"]["unique_transfer_ids"] != expected_audit["count"]:
        raise RuntimeError(f"Transfer audit mismatch: {result['transfer_audit']}")
    if result["accounts_with_wrong_owner_count"] != 0:
        raise RuntimeError("Some accounts do not have exactly one OWNS relationship")
    result["store_bytes"] = folder_bytes(home / "data" / "databases" / "neo4j")
    result["transaction_log_bytes"] = folder_bytes(home / "data" / "transactions" / "neo4j")
    result["store_GB"] = round(result["store_bytes"] / 1_000_000_000, 3)
    result["transaction_log_GB"] = round(result["transaction_log_bytes"] / 1_000_000_000, 3)
    result["status"] = "PASS"
    Path("results").mkdir(exist_ok=True)
    Path("results/neo4j_setup.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
