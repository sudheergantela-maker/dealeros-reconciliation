import sqlite3
from datetime import datetime
from decimal import Decimal


def to_dec(val):
    return Decimal(val) if val is not None else None


def parse_date(date_str: str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def reconcile_org(conn: sqlite3.Connection, org_id: str, date_tolerance_days: int = 3) -> list:
    conn.row_factory = sqlite3.Row

    all_locations = {
        row["location_id"]: dict(row)
        for row in conn.execute("SELECT location_id, org_id, location_name FROM locations").fetchall()
    }
    org_location_ids = {loc_id for loc_id, info in all_locations.items() if info["org_id"] == org_id}
    if not org_location_ids:
        return []

    a_rows = [dict(r) for r in conn.execute("SELECT * FROM system_a").fetchall()]
    b_rows = [dict(r) for r in conn.execute("SELECT * FROM system_b").fetchall()]

    a_by_id = {r["record_id"]: r for r in a_rows}
    b_by_ref = {}
    for r in b_rows:
        b_by_ref.setdefault(r["record_ref"], []).append(r)

    all_ids = sorted(set(a_by_id.keys()) | set(b_by_ref.keys()))
    disagreements = []

    for rec_id in all_ids:
        a_rec = a_by_id.get(rec_id)
        b_list = b_by_ref.get(rec_id, [])

        # Determine owning org strictly from locations.csv
        primary_loc = a_rec["location_id"] if a_rec else b_list[0]["location_id"]
        owner_org = all_locations.get(primary_loc, {}).get("org_id")
        if owner_org != org_id:
            continue

        loc_name = all_locations.get(primary_loc, {}).get("location_name", primary_loc)

        # 1. Orphan in B (exists in System B, not in System A)
        if not a_rec and b_list:
            b_sum = sum((to_dec(b["value"]) or Decimal("0.00")) for b in b_list)
            disagreements.append({
                "record_id": rec_id,
                "reason": "ORPHAN_IN_B",
                "a_value": None,
                "b_value": float(b_sum),
                "difference": float(-b_sum),
                "location": f"{loc_name} ({primary_loc})",
                "details": f"Entry {', '.join(b['entry_id'] for b in b_list)} has no matching System A record.",
            })
            continue

        a_total = to_dec(a_rec["total_value"])
        a_base = to_dec(a_rec["base_value"])

        # 2. Voided in A, still active in B
        if a_rec["state"] == "VOIDED":
            if b_list:
                b_sum = sum((to_dec(b["value"]) or Decimal("0.00")) for b in b_list)
                disagreements.append({
                    "record_id": rec_id,
                    "reason": "VOIDED_IN_SYSTEM_A",
                    "a_value": float(a_total) if a_total is not None else None,
                    "b_value": float(b_sum),
                    "difference": float((a_total or Decimal("0.00")) - b_sum),
                    "location": f"{loc_name} ({primary_loc})",
                    "details": "Marked VOIDED in System A, but active entry exists in System B.",
                })
            continue

        # 3. Missing in B
        if not b_list:
            disagreements.append({
                "record_id": rec_id,
                "reason": "MISSING_IN_B",
                "a_value": float(a_total) if a_total is not None else None,
                "b_value": None,
                "difference": float(a_total) if a_total is not None else None,
                "location": f"{loc_name} ({primary_loc})",
                "details": "Confirmed record in System A has no entry in System B.",
            })
            continue

        # 4. Blank / unparseable value in B (never treated as 0)
        vals = [to_dec(b["value"]) for b in b_list]
        if any(v is None for v in vals):
            disagreements.append({
                "record_id": rec_id,
                "reason": "VALUE_MISMATCH",
                "a_value": float(a_total) if a_total is not None else None,
                "b_value": None,
                "difference": None,
                "location": f"{loc_name} ({primary_loc})",
                "details": "System B value is blank or invalid (stored as NULL, not 0).",
            })
            continue

        # 5. Location mismatch (redacting foreign org location IDs to prevent tenant leakage)
        b_locs = {b["location_id"] for b in b_list}
        if b_locs != {primary_loc}:
            b_sum = sum(vals)
            safe_b_locs = [
                loc if all_locations.get(loc, {}).get("org_id") == org_id else "[REDACTED_EXTERNAL_ORG]"
                for loc in sorted(b_locs)
            ]
            disagreements.append({
                "record_id": rec_id,
                "reason": "LOCATION_MISMATCH",
                "a_value": float(a_total),
                "b_value": float(b_sum),
                "difference": float(a_total - b_sum),
                "location": f"{loc_name} ({primary_loc})",
                "details": f"System A has {primary_loc}, System B has {', '.join(safe_b_locs)}.",
            })
            continue

        # 6. Multiple entries in B: valid split vs duplicate
        b_sum = sum(vals)
        if len(b_list) > 1:
            if a_total is not None and b_sum == a_total:
                continue  # Valid split entry (e.g., REC-1055)
            disagreements.append({
                "record_id": rec_id,
                "reason": "DUPLICATE_IN_B",
                "a_value": float(a_total),
                "b_value": float(b_sum),
                "difference": float(a_total - b_sum),
                "location": f"{loc_name} ({primary_loc})",
                "details": f"{len(b_list)} entries in System B sum to {b_sum} instead of {a_total}.",
            })
            continue

        # 7. Value mismatch against total_value
        if a_total is not None and b_sum != a_total:
            note = " (System B matched base_value instead of total_value)" if a_base == b_sum else ""
            disagreements.append({
                "record_id": rec_id,
                "reason": "VALUE_MISMATCH",
                "a_value": float(a_total),
                "b_value": float(b_sum),
                "difference": float(a_total - b_sum),
                "location": f"{loc_name} ({primary_loc})",
                "details": f"System A total is {a_total}, System B is {b_sum}{note}.",
            })
            continue

        # 8. Date difference beyond tolerance window
        d_a = parse_date(a_rec["event_date"])
        d_b = parse_date(b_list[0]["recorded_on"])
        if d_a and d_b and abs((d_b - d_a).days) > date_tolerance_days:
            disagreements.append({
                "record_id": rec_id,
                "reason": "DATE_MISMATCH",
                "a_value": float(a_total),
                "b_value": float(b_sum),
                "difference": 0.0,
                "location": f"{loc_name} ({primary_loc})",
                "details": f"Date differs by {(d_b - d_a).days} days ({a_rec['event_date']} vs {b_list[0]['recorded_on']}).",
            })

    return disagreements