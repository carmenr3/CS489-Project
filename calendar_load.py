"""
    python calendar_load.py calendar_merged.csv --dry-run       
    $env:MONGODB_URI="mongodb+srv://..."
    python calendar_load.py calendar_merged.csv --db mydb --collection calendar
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def as_int(v):
    return None if pd.isna(v) else int(v)


def as_str(v):
    return None if pd.isna(v) else v


def as_date(v):
    return None if pd.isna(v) else datetime.strptime(v, "%Y-%m-%d")


def as_bool(v):
    if pd.isna(v):
        return None
    return {"t": True, "f": False}.get(v)


def to_doc(row: dict) -> dict:
    return {
        "listing_id": as_int(row["listing_id"]),
        "date": as_date(row["date"]),
        "city": as_str(row["city"]),
        "available": as_bool(row["available"]),
        "minimum_nights": as_int(row["minimum_nights"]),
        "maximum_nights": as_int(row["maximum_nights"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--db", default="airbnb")
    parser.add_argument("--collection", default="calendar")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--dry-run", action="store_true", help="build documents but do not connect or insert")
    args = parser.parse_args()

    coll = None
    if not args.dry_run:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            sys.exit("Set the MONGODB_URI environment variable (or use --dry-run).")
        from pymongo import MongoClient
        from pymongo.errors import BulkWriteError

        coll = MongoClient(uri)[args.db][args.collection]

    total = 0
    shown = 0
    chunks = pd.read_csv(
        args.csv, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8", chunksize=args.batch_size
    )
    for chunk in chunks:
        docs = [to_doc(r) for r in chunk.to_dict("records")]
        if args.dry_run:
            for d in docs[: max(0, 3 - shown)]:
                print(d)
                shown += 1
        else:
            try:
                coll.insert_many(docs, ordered=False)
            except BulkWriteError as e:
                print(f"Batch had {len(e.details['writeErrors'])} write errors (first: {e.details['writeErrors'][0]['errmsg']})")
        total += len(docs)
        print(f"{'Prepared' if args.dry_run else 'Processed'} {total} rows...", end="\r")

    print(f"\nDone. {total} documents {'prepared (dry run)' if args.dry_run else 'sent to MongoDB'}.")


if __name__ == "__main__":
    main()
