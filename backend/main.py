from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from importer import DB_PATH, get_db, import_all_csvs
from reconciler import reconcile_org

app = FastAPI(title="DealerOS Reconciliation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    if not DB_PATH.exists():
        import_all_csvs()


@app.get("/api/orgs")
def list_orgs():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT org_id FROM locations ORDER BY org_id").fetchall()
    conn.close()
    return [r["org_id"] for r in rows]


@app.get("/api/disagreements/")
def get_disagreements(
    org: str = Query(..., description="Tenant org_id, e.g. ORG-A"),
    reason: Optional[str] = Query(default=None),
    sort: str = Query(default="record_id"),
):
    conn = get_db()
    valid_org = conn.execute("SELECT 1 FROM locations WHERE org_id = ?", (org,)).fetchone()
    if not valid_org:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Unknown org: {org}")

    results = reconcile_org(conn, org)
    conn.close()

    if reason and reason != "ALL":
        results = [r for r in results if r["reason"] == reason]

    reverse = sort.startswith("-")
    field = sort.lstrip("-")
    if field in {"a_value", "b_value", "difference"}:
        results.sort(key=lambda x: (x[field] is None, x[field] or 0.0), reverse=reverse)
    else:
        results.sort(key=lambda x: x.get(field, ""), reverse=reverse)

    return {"org": org, "count": len(results), "items": results}