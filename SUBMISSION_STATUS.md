# Submission preparation status

Prepared locally on 15 October 2026.

## Completed

- PostgreSQL and Neo4j data integrity checks
- 61-case SQL/Cypher correctness rerun: 61 passed, 0 failed
- Repeated query benchmarks, including the Neo4j Q2 measured timeouts at 60 seconds
- PostgreSQL and Neo4j concurrency matrices, per-run logs, summaries, and charts
- Required query plans/profiles; PostgreSQL baseline Q7 bound-6 plan timed out at the 180-second collection limit
- Eight reachable Q7 routes verified against PostgreSQL transfer IDs, directions, endpoints, roles, and minimum lengths
- Local source/results archive; `.env`, captured CSVs, and database stores are excluded

## Still needed before submission

- Capture and embed the requested UI screenshots with the taskbar clock visible
- Have each member review their reflection and confirm contribution attribution
- Generate the final PDF after the screenshots and member review are complete
- Add the team's repository URL and create the matching final ZIP

The Windows computer-use tools failed during initialization, so screenshots could not be captured in this session. The PDF creation workflow requires `container_tools/mark_artifact_operation_started.mjs`; that marker script is not available in the accessible workspace/runtime, so no PDF was authored.
