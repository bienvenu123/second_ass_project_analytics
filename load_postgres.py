"""Create/load/verify the project PostgreSQL database using streaming COPY."""
import argparse
import json
import os
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn
import mobile_money_generator as g
from local_config import load_local_env

TABLES = ("customers", "devices", "accounts", "account_devices", "transfers")
COLUMNS = {
    "customers": "customer_id,region",
    "devices": "device_id,access_type",
    "accounts": "account_id,customer_id,role",
    "account_devices": "account_id,device_id,first_day,last_day,observations",
    "transfers": "transfer_id,sender_id,receiver_id,occurred_at,amount_rwf",
}


def main():
    load_local_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--database", default=os.getenv("PG_DATABASE", "mobile_money_project"))
    ap.add_argument("--create", action="store_true", help="create database using PG_ADMIN_DSN if absent")
    args = ap.parse_args()
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        raise SystemExit("Set PG_DSN to connect to the target database (include host, user, password, and dbname).")
    if args.create:
        admin = os.environ.get("PG_ADMIN_DSN")
        if not admin:
            raise SystemExit("Set PG_ADMIN_DSN to an administrative connection before using --create.")
        admin_conn = psycopg2.connect(admin)
        try:
            admin_conn.autocommit = True
            with admin_conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (args.database,))
                if cur.fetchone() is None:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.database)))
                cur.execute(sql.SQL("ALTER DATABASE {} SET timezone TO 'Africa/Kigali'").format(sql.Identifier(args.database)))
        finally:
            admin_conn.close()
    target_parts = parse_dsn(dsn)
    target_parts["dbname"] = args.database
    conn = psycopg2.connect(make_dsn(**target_parts))
    result = {"database": args.database, "table_load_seconds": {}, "rows": {}}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute((Path("postgres_schema.sql")).read_text(encoding="utf-8"))
            for table in TABLES:
                started = time.perf_counter()
                copy = f"COPY {table} ({COLUMNS[table]}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                with conn.cursor() as cur, (args.data / f"{table}.csv").open("r", encoding="utf-8", newline="") as f:
                    cur.copy_expert(copy, f)
                result["table_load_seconds"][table] = round(time.perf_counter() - started, 3)
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
                    result["rows"][table] = cur.fetchone()[0]
                expected = g.dataset_info()["expected_counts"][table]
                if result["rows"][table] != expected:
                    raise RuntimeError(f"{table}: loaded {result['rows'][table]}, expected {expected}")
                print(f"Loaded {table}: {result['rows'][table]:,} rows in {result['table_load_seconds'][table]}s", flush=True)
            started = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(Path("postgres_indexes.sql").read_text(encoding="utf-8"))
            result["index_analyze_seconds"] = round(time.perf_counter() - started, 3)
        with conn.cursor() as cur:
            cur.execute("SELECT role,count(*) FROM accounts GROUP BY role ORDER BY role")
            result["roles"] = {r: n for r, n in cur.fetchall()}
            expected_roles = {"person": 240000, "merchant": 6000, "agent": 2000}
            if result["roles"] != expected_roles:
                raise RuntimeError(f"Account role totals differ from expected: {result['roles']}")
            cur.execute("SELECT count(*),min(occurred_at),max(occurred_at),sum(amount_rwf)::numeric FROM transfers")
            n, lo, hi, total = cur.fetchone()
            result["transfer_audit"] = {"count": n, "earliest_occurred_at": lo,
                                         "latest_occurred_at": hi, "sum_amount_rwf": int(total)}
            if result["transfer_audit"] != json.loads((args.data / "capture_audit.json").read_text(encoding="utf-8"))["transfers"]:
                raise RuntimeError("PostgreSQL transfer audit differs from captured CSV audit")
            cur.execute("""SELECT pg_database_size(current_database()),
                COALESCE(sum(pg_table_size(c.oid)),0),COALESCE(sum(pg_indexes_size(c.oid)),0)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relkind IN ('r','m')""")
            db_bytes, data_bytes, index_bytes = cur.fetchone()
            cur.execute("SELECT pg_indexes_size('transfers'),pg_total_relation_size('transfers')")
            transfer_index_bytes, transfer_table_total = cur.fetchone()
            result["sizes_bytes"] = {"database": db_bytes, "table_and_toast_data": data_bytes,
                                      "indexes": index_bytes, "transfers_indexes": transfer_index_bytes,
                                      "transfers_total": transfer_table_total}
            cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() ORDER BY indexname")
            result["indexes"] = [r[0] for r in cur.fetchall()]
            required_indexes = {
                "accounts_customer_account_idx", "account_devices_device_account_idx",
                "transfers_sender_time_idx", "transfers_receiver_time_idx", "transfers_occurred_brin_idx",
            }
            missing_indexes = sorted(required_indexes - set(result["indexes"]))
            if missing_indexes:
                raise RuntimeError(f"Missing required PostgreSQL indexes: {missing_indexes}")
            cur.execute("SELECT conrelid::regclass::text,conname,contype,convalidated FROM pg_constraint WHERE connamespace=current_schema()::regnamespace ORDER BY 1,2")
            result["constraints"] = [list(r) for r in cur.fetchall()]
            invalid_constraints = [r[1] for r in result["constraints"] if not r[3]]
            if invalid_constraints:
                raise RuntimeError(f"PostgreSQL constraints are not validated: {invalid_constraints}")
            result["verification"] = {"roles_match": True, "required_indexes_present": True,
                                       "all_constraints_validated": True, "transfer_audit_match": True}
        Path("results").mkdir(exist_ok=True)
        Path("results/postgres_load.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        print("Saved results/postgres_load.json")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
