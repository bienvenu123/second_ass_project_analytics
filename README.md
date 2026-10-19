# Mobile Money Analytics Project 2

This workspace contains the supplied fixed-data generator and reproducible project scripts. The generator is intentionally unchanged. The assignment asks for live PostgreSQL and Neo4j runs, timings, screenshots, and a report; those results must come from the student's machine and are not filled with invented values here.

## Runtime facts to record

The brief requires PostgreSQL and a dedicated Neo4j Community instance, with the default Neo4j database named `neo4j`. Record exact versions, Python driver versions, CPU, RAM, operating system, PostgreSQL timezone and memory settings, Neo4j memory settings, load/import times, and actual disk sizes in the report. Keep at least 10 GB available. Use local CSVs and database stores; do not commit them.

## Capture

From this folder, preview the five independent streams, then capture them progressively:

```powershell
python capture.py preview
python capture.py capture --out data
```

The capture writes five CSVs and `data/capture_audit.json`. It checks expected counts as each file closes and records transfer count, earliest/latest epoch and sum. It never holds the complete stream in memory. Preserve the terminal output/screenshots and the audit JSON.

## PostgreSQL

Create the project database, connect with `psql`, and run:

```text
\i postgres_schema.sql
```

Load in dependency order, e.g. from psql (replace the path):

```text
\copy customers FROM 'data/customers.csv' CSV HEADER
\copy devices FROM 'data/devices.csv' CSV HEADER
\copy accounts FROM 'data/accounts.csv' CSV HEADER
\copy account_devices FROM 'data/account_devices.csv' CSV HEADER
\copy transfers FROM 'data/transfers.csv' CSV HEADER
```

The schema includes the required primary/foreign keys and checks. After loading, run `\\i postgres_indexes.sql` to time index setup separately; it builds the required indexes and runs `ANALYZE`. Compare all counts, role counts and transfer audit totals against `capture_audit.json`.

## Neo4j

Prepare disposable typed CSVs:

```powershell
python prepare_import.py --data data --out neo4j_import
```

Stop the empty project database, then run the printed `neo4j-admin database import full neo4j ...` command from the import directory. Start Neo4j and apply:

```cypher
CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE;
CREATE CONSTRAINT account_id IF NOT EXISTS FOR (n:Account) REQUIRE n.account_id IS UNIQUE;
CREATE CONSTRAINT device_id IF NOT EXISTS FOR (n:Device) REQUIRE n.device_id IS UNIQUE;
CREATE INDEX transfer_occurred_at IF NOT EXISTS FOR ()-[r:TRANSFER]-() ON (r.occurred_at);
```

Wait until indexes are online. Verify nodes (704,600), relationships (20,536,900), source row counts, role counts, one owner per account, unique transfer IDs, and audit totals. Remove `neo4j_import` only after successful import and checks.

## Submission checklist

Follow the PDF milestones in order. Keep a run log with command, start/end time, row count, status, and output paths. Include paired query results, 61 correctness comparisons, raw benchmark repetitions, plans, concurrency logs, charts, report, and screenshots with the taskbar and clock visible. Label all measured results with the machine and database settings. Obtain group member names/IDs and individual 150–200 word reflections before finalizing the report. Add your repository URL and create a matching ZIP only after the local output has been reviewed.

Do not infer fraud from these records: the generator explicitly describes device associations as observed use and transfers as incomplete ledger activity.

## Query and reporting helpers

After both databases contain the captured data and the local connection settings are configured:

```powershell
python run_comparisons.py
python benchmark.py --engine postgresql --q7-version baseline
python benchmark.py --engine postgresql --q7-version improved
python benchmark.py --engine neo4j
python concurrency.py --engine postgresql
python concurrency.py --engine neo4j
python make_charts.py
```

`run_neo_smoke.py` records one example per query in `results/neo4j_smoke.json`. `verify_query_samples.py` independently checks its Q1/Q2 totals, Q3 device overlaps, and returned Q5/Q6 transfer paths against the CSVs. Fill `report_draft.md` only with observed measurements and actual group information. Do not present smoke-query timings as the prescribed repeated benchmarks.


Query plan collection: after configuring local connection variables, run `python collect_plans.py`. It writes PostgreSQL EXPLAIN ANALYZE/BUFFERS and Neo4j PROFILE summaries to `results/plans.json`.

Run `python summarize_results.py` to build case medians/minimum/maximum and timeout counts from the raw benchmark JSONL.

Copy `.env.example` to the ignored `.env` file and fill in local credentials before running database commands. The submitted ZIP excludes `.env` and all captured CSV/database stores.

Run `python verify_q7_paths.py` to validate supporting directed, person-only transfer paths and compare their lengths with the 61-case Q7 output.
