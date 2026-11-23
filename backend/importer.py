import csv
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "reconcile.db"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS locations (
            location_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            location_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_a (
            record_id TEXT PRIMARY KEY,
            location_id TEXT,
            event_date TEXT,
            category_code TEXT,
            actor_id TEXT,
            base_value TEXT,
            adjustment TEXT,
            total_value TEXT,
            state TEXT
        );

        CREATE TABLE IF NOT EXISTS system_b (
            entry_id TEXT PRIMARY KEY,
            record_ref_raw TEXT,
            record_ref TEXT,
            location_id TEXT,
            recorded_on TEXT,
            value_raw TEXT,
            value TEXT,
            label TEXT
        );
        """
    )
    conn.commit()


def normalize_record_id(raw_id: str):
    """Normalizes 'rec1034', ' REC - 1070 ', or '1112' -> 'REC-1034'."""
    m = re.search(r"\d+", raw_id or "")
    return f"REC-{m.group()}" if m else None


def parse_amount(raw_val: str):
    """Parses '1,25,400.00' -> Decimal('125400.00'). Blank/invalid -> None (never 0)."""
    cleaned = (raw_val or "").strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def import_all_csvs(data_dir: Path = DATA_DIR, db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    init_db(conn)

    # 1. Load locations.csv
    with open(data_dir / "locations.csv", mode="r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR REPLACE INTO locations (location_id, org_id, location_name) VALUES (?, ?, ?)",
                (row["location_id"].strip(), row["org_id"].strip(), row["location_name"].strip()),
            )

    # 2. Load system_a.csv (idempotent via INSERT OR REPLACE on record_id)
    a_read = 0
    with open(data_dir / "system_a.csv", mode="r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a_read += 1
            raw_id = (row.get("record_id") or "").strip()
            actor = (row.get("actor_id") or "").strip() or None
            base_val = parse_amount(row.get("base_value"))
            adj_val = parse_amount(row.get("adjustment"))
            tot_val = parse_amount(row.get("total_value"))

            conn.execute(
                """
                INSERT OR REPLACE INTO system_a
                (record_id, location_id, event_date, category_code, actor_id,
                 base_value, adjustment, total_value, state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_id,
                    (row.get("location_id") or "").strip(),
                    (row.get("event_date") or "").strip(),
                    (row.get("category_code") or "").strip(),
                    actor,
                    str(base_val) if base_val is not None else None,
                    str(adj_val) if adj_val is not None else None,
                    str(tot_val) if tot_val is not None else None,
                    (row.get("state") or "").strip().upper(),
                ),
            )

    # 3. Load system_b.csv (idempotent via INSERT OR REPLACE on entry_id)
    b_read = 0
    refs_cleaned = 0
    blanks_kept = 0
    with open(data_dir / "system_b.csv", mode="r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            b_read += 1
            raw_ref = (row.get("record_ref") or "").strip()
            norm_ref = normalize_record_id(raw_ref)
            if norm_ref and norm_ref != raw_ref:
                refs_cleaned += 1

            raw_val = (row.get("value") or "").strip()
            dec_val = parse_amount(raw_val)
            if dec_val is None:
                blanks_kept += 1

            conn.execute(
                """
                INSERT OR REPLACE INTO system_b
                (entry_id, record_ref_raw, record_ref, location_id, recorded_on,
                 value_raw, value, label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (row.get("entry_id") or "").strip(),
                    raw_ref,
                    norm_ref,
                    (row.get("location_id") or "").strip(),
                    (row.get("recorded_on") or "").strip(),
                    raw_val,
                    str(dec_val) if dec_val is not None else None,
                    (row.get("label") or "").strip(),
                ),
            )

    conn.commit()
    a_saved = conn.execute("SELECT COUNT(*) FROM system_a").fetchone()[0]
    b_saved = conn.execute("SELECT COUNT(*) FROM system_b").fetchone()[0]
    conn.close()
    print(f"A: {a_read} read, {a_saved} saved | B: {b_read} read, {b_saved} saved | blanks: {blanks_kept} | refs cleaned: {refs_cleaned}")


if __name__ == "__main__":
    import_all_csvs()