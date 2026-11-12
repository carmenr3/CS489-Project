"""
    python calendar_transform.py portland_calendar.csv la_calendar.csv ... -o calendar_merged.csv
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

KEEP = ["listing_id", "date", "available", "minimum_nights", "maximum_nights"]
OUT_COLS = ["listing_id", "date", "city", "available", "minimum_nights", "maximum_nights"]
INT_COLS = ["listing_id", "minimum_nights", "maximum_nights"]
FILENAME_NOISE = {"example", "calendar"}
BOOL_MAP = {"t": "t", "true": "t", "f": "f", "false": "f"}
CHUNK_SIZE = 500_000
EPOCH = pd.Timestamp("1970-01-01")


def city_from_filename(path: Path) -> str:
    """portland_example_calendar.csv -> portland ; Los Angeles-calendar.csv -> los_angeles"""
    stem = re.sub(r"[\s\-]+", "_", path.stem.lower())
    tokens = [t for t in stem.split("_") if t and t not in FILENAME_NOISE]
    if not tokens:
        raise ValueError(f"Could not work out a city name from file name: {path.name}")
    return "_".join(tokens)


def read_chunks(path: Path):
    return pd.read_csv(
        path,
        usecols=KEEP,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8-sig",
        chunksize=CHUNK_SIZE,
    )


def check_columns(path: Path) -> None:
    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns
    missing = [c for c in KEEP if c not in header]
    if missing:
        sys.exit(f"{path.name}: missing expected columns {missing}. Found: {list(header)}")


def transform_chunk(chunk: pd.DataFrame, city: str, stats: dict):
    chunk = chunk[KEEP].copy()

    for col in INT_COLS:
        chunk[col] = pd.to_numeric(chunk[col], errors="coerce").astype("Int64")

    dates = pd.to_datetime(chunk["date"], format="%Y-%m-%d", errors="coerce")
    stats["bad_dates"] += int((dates.isna() & chunk["date"].notna()).sum())
    chunk["date"] = dates.dt.strftime("%Y-%m-%d")

    raw = chunk["available"].str.strip().str.lower()
    mapped = raw.map(BOOL_MAP)
    stats["bad_available"] += int((raw.notna() & mapped.isna()).sum())
    chunk["available"] = mapped

    chunk["city"] = city

    days = (dates - EPOCH).dt.days.astype("Int64")
    keys = chunk["listing_id"] * 100_000 + days
    return chunk[OUT_COLS], keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="input CSV files (same format)")
    parser.add_argument("-o", "--output", type=Path, default=Path("calendar_merged.csv"))
    parser.add_argument("--no-dedupe", action="store_true", help="skip duplicate removal (saves memory)")
    args = parser.parse_args()

    for f in args.files:
        if not f.is_file():
            sys.exit(f"File not found: {f}")
        check_columns(f)

    seen: dict[str, set[int]] = {}
    first_write = True
    total_written = 0

    for path in args.files:
        city = city_from_filename(path)
        city_seen = seen.setdefault(city, set())
        stats = {"read": 0, "written": 0, "dupes": 0, "bad_dates": 0, "bad_available": 0}

        for chunk in read_chunks(path):
            stats["read"] += len(chunk)
            out, keys = transform_chunk(chunk, city, stats)

            if not args.no_dedupe:
                keep_mask = []
                for k in keys:
                    if pd.isna(k):
                        keep_mask.append(True)
                    elif int(k) in city_seen:
                        keep_mask.append(False)
                    else:
                        city_seen.add(int(k))
                        keep_mask.append(True)
                out = out[keep_mask]
                stats["dupes"] += len(keep_mask) - len(out)

            out.to_csv(
                args.output,
                mode="w" if first_write else "a",
                header=first_write,
                index=False,
                encoding="utf-8",
            )
            first_write = False
            stats["written"] += len(out)

        total_written += stats["written"]
        print(
            f"{path.name}: city='{city}' read={stats['read']} written={stats['written']} "
            f"duplicates_dropped={stats['dupes']} unparseable_dates={stats['bad_dates']} "
            f"unrecognised_available={stats['bad_available']}"
        )

    print(f"Done. {total_written} rows written to {args.output}")


if __name__ == "__main__":
    main()
