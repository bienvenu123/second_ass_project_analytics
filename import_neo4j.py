"""Stage typed files and run a full import into a stopped, empty Neo4j DBMS."""
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

FILES = ("customers_import.csv", "accounts_import.csv", "devices_import.csv",
         "owns.csv", "used_device.csv", "transfers_import.csv")
BASE_ARGS = ("database", "import", "full", "neo4j", "--id-type=integer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neo4j-home", type=Path, required=True)
    ap.add_argument("--prepared", type=Path, default=Path("neo4j_import"))
    ap.add_argument("--java-home", type=Path, default=Path(os.environ.get("JAVA_HOME", r"C:\Program Files\Java\jdk-21")))
    args = ap.parse_args()
    home = args.neo4j_home.resolve()
    prepared = args.prepared.resolve()
    admin = home / "bin" / "neo4j-admin.bat"
    import_dir = home / "import"
    if not admin.is_file():
        raise SystemExit(f"neo4j-admin not found: {admin}")
    if not prepared.is_dir():
        raise SystemExit(f"Prepared import directory not found: {prepared}")
    missing = [n for n in FILES if not (prepared / n).is_file()]
    if missing:
        raise SystemExit(f"Missing prepared files: {missing}")
    import_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(prepared / name, import_dir / name)
    import_args = [*BASE_ARGS,
        f"--nodes=Customer={(import_dir / FILES[0]).resolve()}",
        f"--nodes=Account={(import_dir / FILES[1]).resolve()}",
        f"--nodes=Device={(import_dir / FILES[2]).resolve()}",
        f"--relationships=OWNS={(import_dir / FILES[3]).resolve()}",
        f"--relationships=USED_DEVICE={(import_dir / FILES[4]).resolve()}",
        f"--relationships=TRANSFER={(import_dir / FILES[5]).resolve()}"]
    cmd = subprocess.list2cmdline([str(admin), *import_args])
    started = time.perf_counter()
    env = os.environ.copy()
    java_home = args.java_home.resolve()
    if not (java_home / "bin" / "java.exe").is_file():
        raise SystemExit(f"Java runtime not found under {java_home}; Neo4j 2026 requires Java 21+")
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(["cmd.exe", "/c", cmd], cwd=home / "bin", env=env, check=False)
    seconds = round(time.perf_counter() - started, 3)
    if proc.returncode:
        raise SystemExit(f"neo4j-admin import failed with exit code {proc.returncode}")
    Path("results").mkdir(exist_ok=True)
    data = {"database": "neo4j", "neo4j_home": str(home), "import_seconds": seconds,
            "java_home": str(java_home),
            "source_files": {n: (prepared / n).stat().st_size for n in FILES}}
    Path("results/neo4j_import.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
