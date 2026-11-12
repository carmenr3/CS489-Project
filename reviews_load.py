"""
    python load.py merged.csv --dry-run                 
    set MONGODB_URI=mongodb+srv://...                   "
    python load.py merged.csv --db mydb --collection reviews
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


def to_doc(row: dict) -> dict:
    reviewer_id = as_int(row["reviewer_id"])
    reviewer_name = as_str(row["reviewer_name"])
    reviewer = None if reviewer_id is None and reviewer_name is None else {"id": reviewer_id, "name": reviewer_name}
    return {
        "listing_id": as_int(row["listing_id"]),
        "id": as_int(row["id"]),
        "date": as_date(row["date"]),
        "month": as_int(row["month"]),
        "city": as_str(row["city"]),
        "reviewer": reviewer,
        "comments": as_str(row["comments"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--db", default="airbnb")
    parser.add_argument("--collection", default="reviews")
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
