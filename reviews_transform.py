"""
    python transform.py portland_Reviews.csv los_angeles_Reviews.csv ... -o reviews_merged.csv
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

KEEP = ["listing_id", "id", "date", "reviewer_id", "reviewer_name", "comments"]
OUT_COLS = ["listing_id", "id", "date", "month", "city", "reviewer_id", "reviewer_name", "comments"]
INT_COLS = ["listing_id", "id", "reviewer_id"]
TEXT_COLS = ["reviewer_name", "comments"]
FILENAME_NOISE = {"review", "reviews"}
CHUNK_SIZE = 200_000


def city_from_filename(path: Path) -> str:
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


def transform_chunk(chunk: pd.DataFrame, city: str, stats: dict) -> pd.DataFrame:
    chunk = chunk[KEEP].copy()

    for col in INT_COLS:
        chunk[col] = pd.to_numeric(chunk[col], errors="coerce").astype("Int64")

    dates = pd.to_datetime(chunk["date"], format="%Y-%m-%d", errors="coerce")
    stats["bad_dates"] += int((dates.isna() & chunk["date"].notna()).sum())
    chunk["month"] = dates.dt.month.astype("Int64")
    chunk["date"] = dates.dt.strftime("%Y-%m-%d")  # NaT -> NaN -> written as empty

    for col in TEXT_COLS:  # whitespace-only text counts as empty
        blank = chunk[col].str.strip().eq("")
        chunk.loc[blank, col] = pd.NA

    chunk["city"] = city
    return chunk[OUT_COLS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="input CSV files (same format)")
    parser.add_argument("-o", "--output", type=Path, default=Path("merged.csv"))
    args = parser.parse_args()

    for f in args.files:
        if not f.is_file():
            sys.exit(f"File not found: {f}")
        check_columns(f)

    seen: set[tuple[str, int, int]] = set()
    first_write = True
    total_written = 0

    for path in args.files:
        city = city_from_filename(path)
        stats = {"read": 0, "written": 0, "dupes": 0, "bad_dates": 0}

        for chunk in read_chunks(path):
            stats["read"] += len(chunk)
            out = transform_chunk(chunk, city, stats)

            keep_mask = []
            for lid, rid in zip(out["listing_id"], out["id"]):
                if pd.isna(rid) or pd.isna(lid):
                    keep_mask.append(True)
                    continue
                key = (city, int(lid), int(rid))
                if key in seen:
                    keep_mask.append(False)
                else:
                    seen.add(key)
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
            f"duplicates_dropped={stats['dupes']} unparseable_dates={stats['bad_dates']}"
        )

    print(f"Done. {total_written} rows written to {args.output}")


if __name__ == "__main__":
    main()
