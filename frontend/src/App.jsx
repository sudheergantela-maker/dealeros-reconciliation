import React, { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000/api";

const REASONS = [
  "ALL",
  "VALUE_MISMATCH",
  "MISSING_IN_B",
  "ORPHAN_IN_B",
  "DUPLICATE_IN_B",
  "VOIDED_IN_SYSTEM_A",
  "LOCATION_MISMATCH",
  "DATE_MISMATCH",
];

function formatMoney(val) {
  if (val === null || val === undefined) return "";
  return Number(val).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function App() {
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState("ORG-A");
  const [reasonFilter, setReasonFilter] = useState("ALL");
  const [sortParam, setSortParam] = useState("record_id");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/orgs`)
      .then((res) => res.json())
      .then((data) => {
        setOrgs(data);
        if (data.length > 0 && !data.includes(selectedOrg)) {
          setSelectedOrg(data[0]);
        }
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    const params = new URLSearchParams({
      org: selectedOrg,
      sort: sortParam,
    });
    if (reasonFilter !== "ALL") {
      params.set("reason", reasonFilter);
    }
    fetch(`${API_BASE}/disagreements/?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => setRows(data.items || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedOrg, reasonFilter, sortParam]);

  const toggleSort = (field) => {
    setSortParam((prev) => (prev === field ? `-${field}` : field));
  };

  const sortArrow = (field) => {
    if (sortParam === field) return " ↑";
    if (sortParam === `-${field}`) return " ↓";
    return "";
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "32px auto", padding: "0 16px" }}>
      <h1 style={{ marginBottom: "4px" }}>DealerOS Ledger Reconciliation</h1>
      <p style={{ color: "#475569", marginTop: 0 }}>
        System A vs System B disagreements isolated by tenant organization.
      </p>

      <div
        style={{
          display: "flex",
          gap: "16px",
          flexWrap: "wrap",
          background: "#fff",
          padding: "16px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0",
          marginBottom: "16px",
        }}
      >
        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
            Tenant (Org)
          </label>
          <select
            value={selectedOrg}
            onChange={(e) => setSelectedOrg(e.target.value)}
            style={{ padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
          >
            {orgs.map((org) => (
              <option key={org} value={org}>
                {org}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
            Filter by Reason
          </label>
          <select
            value={reasonFilter}
            onChange={(e) => setReasonFilter(e.target.value)}
            style={{ padding: "8px 12px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
          >
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginLeft: "auto", alignSelf: "flex-end", fontSize: "14px", color: "#334155" }}>
          Showing <strong>{rows.length}</strong> disagreement(s) for <strong>{selectedOrg}</strong>
        </div>
      </div>

      <div style={{ background: "#fff", borderRadius: "8px", border: "1px solid #e2e8f0", overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "#f1f5f9", borderBottom: "1px solid #e2e8f0" }}>
              <th style={thStyle}>Reason</th>
              <th style={thStyle} onClick={() => toggleSort("record_id")}>
                Record ID{sortArrow("record_id")}
              </th>
              <th style={thStyle}>Location</th>
              <th style={{ ...thStyle, textAlign: "right" }} onClick={() => toggleSort("a_value")}>
                System A Value{sortArrow("a_value")}
              </th>
              <th style={{ ...thStyle, textAlign: "right" }} onClick={() => toggleSort("b_value")}>
                System B Value{sortArrow("b_value")}
              </th>
              <th style={{ ...thStyle, textAlign: "right" }} onClick={() => toggleSort("difference")}>
                Difference{sortArrow("difference")}
              </th>
              <th style={thStyle}>Notes</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ padding: "24px", textAlign: "center" }}>
                  Loading...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: "24px", textAlign: "center", color: "#64748b" }}>
                  No disagreements found for {selectedOrg}.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.record_id} style={{ borderBottom: "1px solid #e2e8f0" }}>
                  <td style={tdStyle}>
                    <span
                      style={{
                        background: "#fee2e2",
                        color: "#991b1b",
                        padding: "3px 8px",
                        borderRadius: "4px",
                        fontSize: "12px",
                        fontWeight: 600,
                      }}
                    >
                      {row.reason}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <strong>{row.record_id}</strong>
                  </td>
                  <td style={tdStyle}>{row.location}</td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: "monospace" }}>
                    {formatMoney(row.a_value)}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: "monospace" }}>
                    {formatMoney(row.b_value)}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: "monospace", fontWeight: 600 }}>
                    {formatMoney(row.difference)}
                  </td>
                  <td style={{ ...tdStyle, fontSize: "13px", color: "#475569" }}>{row.details}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const thStyle = {
  padding: "12px 14px",
  fontSize: "13px",
  fontWeight: 600,
  cursor: "pointer",
  userSelect: "none",
};

const tdStyle = {
  padding: "12px 14px",
  fontSize: "14px",
};