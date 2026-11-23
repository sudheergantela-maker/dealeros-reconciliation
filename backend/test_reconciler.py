import sqlite3
from importer import import_all_csvs, init_db, normalize_record_id, parse_amount
from reconciler import reconcile_org


def setup_memory_db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.executemany(
        "INSERT INTO locations VALUES (?, ?, ?)",
        [
            ("LOC-101", "ORG-A", "Location 101"),
            ("LOC-201", "ORG-B", "Location 201"),
        ],
    )
    return conn


def test_missing_in_b():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-1", "LOC-101", "2026-04-01", "500.00", "CONFIRMED"),
    )
    res = reconcile_org(conn, "ORG-A")
    assert len(res) == 1
    assert res[0]["reason"] == "MISSING_IN_B"


def test_orphan_in_b():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        ("ENT-1", "REC-2", "REC-2", "LOC-101", "2026-04-01", "300.00"),
    )
    res = reconcile_org(conn, "ORG-A")
    assert len(res) == 1
    assert res[0]["reason"] == "ORPHAN_IN_B"


def test_duplicate_in_b():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-DUP", "LOC-101", "2026-04-01", "100.00", "CONFIRMED"),
    )
    conn.executemany(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        [
            ("E1", "REC-DUP", "REC-DUP", "LOC-101", "2026-04-01", "100.00"),
            ("E2", "REC-DUP", "REC-DUP", "LOC-101", "2026-04-01", "100.00"),
        ],
    )
    res = reconcile_org(conn, "ORG-A")
    assert len(res) == 1
    assert res[0]["reason"] == "DUPLICATE_IN_B"


def test_value_mismatch():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, base_value, total_value, state) VALUES (?,?,?,?,?,?)",
        ("REC-3", "LOC-101", "2026-04-01", "100.00", "128.00", "CONFIRMED"),
    )
    conn.execute(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        ("E5", "REC-3", "REC-3", "LOC-101", "2026-04-01", "100.00"),
    )
    res = reconcile_org(conn, "ORG-A")
    assert len(res) == 1
    assert res[0]["reason"] == "VALUE_MISMATCH"


def test_blank_value_not_zero():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-6", "LOC-101", "2026-04-01", "0.00", "CONFIRMED"),
    )
    conn.execute(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value_raw, value) VALUES (?,?,?,?,?,?,?)",
        ("E8", "REC-6", "REC-6", "LOC-101", "2026-04-01", "", None),
    )
    res = reconcile_org(conn, "ORG-A")
    assert len(res) == 1
    assert res[0]["reason"] == "VALUE_MISMATCH"
    assert res[0]["b_value"] is None


def test_split_entries_that_add_up_not_flagged():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-SPLIT", "LOC-101", "2026-04-01", "100.00", "CONFIRMED"),
    )
    conn.executemany(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        [
            ("E3", "REC-SPLIT", "REC-SPLIT", "LOC-101", "2026-04-01", "40.00"),
            ("E4", "REC-SPLIT", "REC-SPLIT", "LOC-101", "2026-04-01", "60.00"),
        ],
    )
    assert reconcile_org(conn, "ORG-A") == []


def test_messy_references_and_comma_amounts_not_flagged():
    assert normalize_record_id("rec1034") == "REC-1034"
    assert normalize_record_id(" REC - 1070 ") == "REC-1070"
    assert normalize_record_id("1112") == "REC-1112"
    assert str(parse_amount("1,25,400.00")) == "125400.00"


def test_clean_row_not_flagged():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-10", "LOC-101", "2026-04-01", "250.50", "CONFIRMED"),
    )
    conn.execute(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        ("E10", "rec10", "REC-10", "LOC-101", "2026-04-01", "250.50"),
    )
    assert reconcile_org(conn, "ORG-A") == []


def test_tenant_isolation_and_cross_org_trap():
    conn = setup_memory_db()
    conn.execute(
        "INSERT INTO system_a (record_id, location_id, event_date, total_value, state) VALUES (?,?,?,?,?)",
        ("REC-5", "LOC-101", "2026-04-01", "200.00", "CONFIRMED"),
    )
    conn.execute(
        "INSERT INTO system_b (entry_id, record_ref_raw, record_ref, location_id, recorded_on, value) VALUES (?,?,?,?,?,?)",
        ("E7", "REC-5", "REC-5", "LOC-201", "2026-04-01", "200.00"),
    )
    res_a = reconcile_org(conn, "ORG-A")
    res_b = reconcile_org(conn, "ORG-B")
    assert len(res_a) == 1
    assert "LOC-201" not in res_a[0]["details"]
    assert len(res_b) == 0


def test_real_dataset_end_to_end(tmp_path):
    db_file = tmp_path / "test.db"
    import_all_csvs(db_path=db_file)
    conn = sqlite3.connect(db_file)

    org_a = reconcile_org(conn, "ORG-A")
    org_b = reconcile_org(conn, "ORG-B")

    assert {r["record_id"] for r in org_a} == {
        "REC-1015", "REC-1027", "REC-1042", "REC-1064", "REC-1077", "REC-1088", "REC-1999"
    }
    assert {r["record_id"] for r in org_b} == {
        "REC-1003", "REC-1019", "REC-1050", "REC-1061"
    }