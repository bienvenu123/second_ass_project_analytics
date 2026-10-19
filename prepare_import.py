"""Create disposable, typed Neo4j admin-import CSVs from capture CSVs."""
import argparse
import csv
from pathlib import Path


def convert(src: Path, dst: Path, header, transform):
    with src.open(newline="", encoding="utf-8") as inf, dst.open("w", newline="", encoding="utf-8") as outf:
        reader = csv.DictReader(inf)
        writer = csv.writer(outf)
        writer.writerow(header)
        for row in reader:
            writer.writerow(transform(row))


def prepare(data: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    convert(data / "customers.csv", out / "customers_import.csv",
            ["customer_id:ID(Customer)", "region:string"],
            lambda r: [r["customer_id"], r["region"]])
    convert(data / "accounts.csv", out / "accounts_import.csv",
            ["account_id:ID(Account)", "customer_id:IGNORE", "role:string"],
            lambda r: [r["account_id"], r["customer_id"], r["role"]])
    convert(data / "devices.csv", out / "devices_import.csv",
            ["device_id:ID(Device)", "access_type:string"],
            lambda r: [r["device_id"], r["access_type"]])
    convert(data / "accounts.csv", out / "owns.csv",
            [":START_ID(Customer)", ":END_ID(Account)", ":TYPE"],
            lambda r: [r["customer_id"], r["account_id"], "OWNS"])
    convert(data / "account_devices.csv", out / "used_device.csv",
            [":START_ID(Account)", ":END_ID(Device)", "first_day:int", "last_day:int", "observations:int", ":TYPE"],
            lambda r: [r["account_id"], r["device_id"], r["first_day"], r["last_day"], r["observations"], "USED_DEVICE"])
    convert(data / "transfers.csv", out / "transfers_import.csv",
            ["transfer_id:long", ":START_ID(Account)", ":END_ID(Account)", "occurred_at:long", "amount_rwf:int", ":TYPE"],
            lambda r: [r["transfer_id"], r["sender_id"], r["receiver_id"], r["occurred_at"], r["amount_rwf"], "TRANSFER"])
    print(f"Prepared Neo4j import files in {out}")
    print("Run neo4j-admin database import full neo4j --id-type=integer --nodes=Customer=customers_import.csv --nodes=Account=accounts_import.csv --nodes=Device=devices_import.csv --relationships=OWNS=owns.csv --relationships=USED_DEVICE=used_device.csv --relationships=TRANSFER=transfers_import.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("neo4j_import"))
    a = ap.parse_args()
    prepare(a.data, a.out)
