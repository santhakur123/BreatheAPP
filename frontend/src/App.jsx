import { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [user, setUser] = useState(null);

  const login = async (username, password) => {
    const res = await fetch(`${API}/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error("Invalid credentials");
    const data = await res.json();
    localStorage.setItem("token", data.token);
    setToken(data.token);
    setUser(data);
    return data;
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  useEffect(() => {
    if (token && !user) {
      fetch(`${API}/auth/me/`, { headers: { Authorization: `Token ${token}` } })
        .then((r) => r.json())
        .then(setUser)
        .catch(logout);
    }
  }, [token]);

  return { token, user, login, logout };
}

function apiFetch(path, token, opts = {}) {
  return fetch(`${API}${path}`, {
    ...opts,
    headers: { Authorization: `Token ${token}`, ...(opts.headers || {}) },
  }).then((r) => {
    if (!r.ok) throw new Error(`API error ${r.status}`);
    return r.json();
  });
}

// ---- Login Screen ----
function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("breathe2024");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await onLogin(username, password);
    } catch {
      setError("Invalid credentials. Try analyst / breathe2024");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.loginWrap}>
      <div style={styles.loginCard}>
        <div style={styles.loginLogo}>
          <span style={styles.logoLeaf}>🌿</span>
          <h1 style={styles.loginTitle}>Breathe ESG</h1>
          <p style={styles.loginSub}>Emissions Review Platform</p>
        </div>
        <form onSubmit={submit}>
          <input
            style={styles.input}
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            style={styles.input}
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p style={styles.error}>{error}</p>}
          <button style={styles.btnPrimary} disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <p style={styles.loginHint}>Demo: analyst / breathe2024</p>
      </div>
    </div>
  );
}

// ---- Dashboard Summary Cards ----
function SummaryCards({ summary }) {
  if (!summary) return <div style={styles.loading}>Loading summary…</div>;
  const cards = [
    { label: "Total CO₂e", value: `${(+summary.total_co2e_kg / 1000).toFixed(1)} tCO₂e`, color: "#1a472a" },
    { label: "Scope 1 (Fuel)", value: `${(+summary.scope1_co2e_kg / 1000).toFixed(1)} t`, color: "#2d6a4f" },
    { label: "Scope 2 (Electricity)", value: `${(+summary.scope2_co2e_kg / 1000).toFixed(1)} t`, color: "#40916c" },
    { label: "Scope 3 (Travel)", value: `${(+summary.scope3_co2e_kg / 1000).toFixed(1)} t`, color: "#52b788" },
    { label: "Pending Review", value: summary.pending_count, color: "#e9c46a", dark: true },
    { label: "Flagged", value: summary.flagged_count, color: "#e76f51", dark: true },
    { label: "Approved", value: summary.approved_count, color: "#2a9d8f" },
    { label: "Total Records", value: summary.total_records, color: "#264653" },
  ];

  return (
    <div style={styles.cardGrid}>
      {cards.map((c) => (
        <div key={c.label} style={{ ...styles.card, background: c.color }}>
          <div style={{ ...styles.cardValue, color: c.dark ? "#1a1a1a" : "#fff" }}>{c.value}</div>
          <div style={{ ...styles.cardLabel, color: c.dark ? "#333" : "rgba(255,255,255,0.85)" }}>{c.label}</div>
        </div>
      ))}
    </div>
  );
}

// ---- Category Breakdown ----
function CategoryBreakdown({ summary }) {
  if (!summary?.by_category?.length) return null;
  const maxVal = Math.max(...summary.by_category.map((c) => +c.co2e_kg));

  return (
    <div style={styles.section}>
      <h3 style={styles.sectionTitle}>Emissions by Category</h3>
      {summary.by_category.slice(0, 10).map((cat) => (
        <div key={cat.category} style={styles.barRow}>
          <div style={styles.barLabel}>
            <span style={styles.scopeBadge(cat.scope)}>S{cat.scope}</span>
            {cat.category.replace(/_/g, " ")}
          </div>
          <div style={styles.barTrack}>
            <div
              style={{
                ...styles.barFill,
                width: `${(+cat.co2e_kg / maxVal) * 100}%`,
                background: cat.scope === 1 ? "#2d6a4f" : cat.scope === 2 ? "#40916c" : "#52b788",
              }}
            />
          </div>
          <div style={styles.barValue}>{(+cat.co2e_kg / 1000).toFixed(2)} t</div>
        </div>
      ))}
    </div>
  );
}

// ---- Record Table ----
function RecordTable({ token, onReview }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ review_status: "", scope: "", is_flagged: "" });
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [selected, setSelected] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page });
      if (filter.review_status) params.set("review_status", filter.review_status);
      if (filter.scope) params.set("scope", filter.scope);
      if (filter.is_flagged) params.set("is_flagged", filter.is_flagged);
      const data = await apiFetch(`/emissions/records/?${params}`, token);
      setRecords(data.results || []);
      setCount(data.count || 0);
    } finally {
      setLoading(false);
    }
  }, [token, filter, page]);

  useEffect(() => { load(); }, [load]);

  const handleBulkApprove = async () => {
    await apiFetch("/emissions/records/bulk_approve/", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: selected }),
    });
    setSelected([]);
    load();
  };

  const statusColor = { pending: "#e9c46a", approved: "#2a9d8f", rejected: "#e76f51", flagged: "#f4a261" };

  return (
    <div style={styles.section}>
      <div style={styles.tableHeader}>
        <h3 style={styles.sectionTitle}>Emission Records</h3>
        <div style={styles.filters}>
          <select style={styles.select} value={filter.review_status} onChange={(e) => setFilter({ ...filter, review_status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="flagged">Flagged</option>
            <option value="rejected">Rejected</option>
          </select>
          <select style={styles.select} value={filter.scope} onChange={(e) => setFilter({ ...filter, scope: e.target.value })}>
            <option value="">All scopes</option>
            <option value="1">Scope 1</option>
            <option value="2">Scope 2</option>
            <option value="3">Scope 3</option>
          </select>
          <select style={styles.select} value={filter.is_flagged} onChange={(e) => setFilter({ ...filter, is_flagged: e.target.value })}>
            <option value="">All</option>
            <option value="true">Flagged only</option>
            <option value="false">Not flagged</option>
          </select>
          {selected.length > 0 && (
            <button style={styles.btnSmall} onClick={handleBulkApprove}>
              Approve {selected.length} selected
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div style={styles.loading}>Loading records…</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}><input type="checkbox" onChange={(e) => setSelected(e.target.checked ? records.map((r) => r.id) : [])} /></th>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>Scope</th>
                <th style={styles.th}>Category</th>
                <th style={styles.th}>Quantity</th>
                <th style={styles.th}>CO₂e (kg)</th>
                <th style={styles.th}>Source</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Flag</th>
                <th style={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} style={r.is_flagged ? styles.flaggedRow : styles.row}>
                  <td style={styles.td}>
                    <input
                      type="checkbox"
                      checked={selected.includes(r.id)}
                      onChange={(e) =>
                        setSelected(e.target.checked ? [...selected, r.id] : selected.filter((s) => s !== r.id))
                      }
                    />
                  </td>
                  <td style={styles.td}>{r.activity_date}</td>
                  <td style={styles.td}><span style={styles.scopeBadge(r.scope)}>S{r.scope}</span></td>
                  <td style={styles.td}>{r.category.replace(/_/g, " ")}</td>
                  <td style={styles.td}>{(+r.activity_quantity).toFixed(2)} {r.activity_unit}</td>
                  <td style={styles.td}><strong>{(+r.co2e_kg).toFixed(2)}</strong></td>
                  <td style={styles.tdSmall}>{r.batch_source_type?.replace(/_/g, " ")}</td>
                  <td style={styles.td}>
                    <span style={{ ...styles.badge, background: statusColor[r.review_status] }}>
                      {r.review_status}
                    </span>
                  </td>
                  <td style={styles.td}>{r.is_flagged ? "⚠️" : ""}</td>
                  <td style={styles.td}>
                    <button style={styles.btnXs("#2a9d8f")} onClick={() => onReview(r, "approve", load)}>✓</button>
                    <button style={styles.btnXs("#e76f51")} onClick={() => onReview(r, "reject", load)}>✗</button>
                    <button style={styles.btnXs("#e9c46a")} onClick={() => onReview(r, "flag", load)}>⚑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={styles.pagination}>
        <span style={{ color: "#aaa" }}>{count} records total</span>
        <button style={styles.pageBtn} disabled={page === 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
        <span style={{ color: "#ccc" }}>Page {page}</span>
        <button style={styles.pageBtn} disabled={records.length < 50} onClick={() => setPage((p) => p + 1)}>Next →</button>
      </div>
    </div>
  );
}

// ---- Ingest Panel ----
function IngestPanel({ token, onDone }) {
  const [activeTab, setActiveTab] = useState("sap");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const endpoints = { sap: "/ingestion/sap/", utility: "/ingestion/utility/", travel: "/ingestion/travel/" };
  const labels = { sap: "SAP Flat File (.txt/.csv tab-separated)", utility: "Utility Portal CSV", travel: "Travel JSON (Navan/Concur)" };

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}${endpoints[activeTab]}`, {
        method: "POST",
        headers: { Authorization: `Token ${token}` },
        body: form,
      });
      const data = await res.json();
      setResult(data);
      onDone();
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.section}>
      <h3 style={styles.sectionTitle}>Ingest Data</h3>
      <div style={styles.tabs}>
        {Object.keys(endpoints).map((t) => (
          <button key={t} style={activeTab === t ? styles.tabActive : styles.tab} onClick={() => { setActiveTab(t); setFile(null); setResult(null); }}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      <p style={{ color: "#aaa", fontSize: 13, marginBottom: 12 }}>{labels[activeTab]}</p>
      <input type="file" style={styles.fileInput} onChange={(e) => setFile(e.target.files[0])} />
      <button style={styles.btnPrimary} onClick={submit} disabled={!file || loading}>
        {loading ? "Uploading…" : "Upload & Ingest"}
      </button>
      {result && (
        <div style={result.error ? styles.errorBox : styles.successBox}>
          {result.error ? (
            <p>Error: {result.error}</p>
          ) : (
            <>
              <p>✓ Batch {result.batch_id?.slice(0, 8)}… — {result.accepted} accepted, {result.rejected} rejected</p>
              {result.errors?.length > 0 && (
                <details>
                  <summary style={{ cursor: "pointer", color: "#e9c46a" }}>{result.errors.length} parse errors</summary>
                  <pre style={{ fontSize: 11, color: "#aaa", maxHeight: 200, overflow: "auto" }}>
                    {JSON.stringify(result.errors, null, 2)}
                  </pre>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---- Review Modal ----
function ReviewModal({ record, action, token, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await apiFetch(`/emissions/records/${record.id}/review/`, token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, review_note: note, reason: note }),
      });
      onDone();
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const actionLabels = { approve: "Approve", reject: "Reject", flag: "Flag for Review" };
  const actionColors = { approve: "#2a9d8f", reject: "#e76f51", flag: "#e9c46a" };

  return (
    <div style={styles.modalOverlay}>
      <div style={styles.modal}>
        <h3 style={{ color: "#fff", marginBottom: 8 }}>{actionLabels[action]} Record</h3>
        <p style={{ color: "#aaa", fontSize: 13 }}>{record.category.replace(/_/g, " ")} | {record.activity_date} | {(+record.co2e_kg).toFixed(2)} kg CO₂e</p>
        {record.is_flagged && <div style={styles.flagWarning}>⚠️ {record.flag_reason}</div>}
        <textarea
          style={styles.textarea}
          placeholder="Optional note for audit trail…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div style={styles.modalActions}>
          <button style={styles.btnCancel} onClick={onClose}>Cancel</button>
          <button style={{ ...styles.btnPrimary, background: actionColors[action] }} onClick={submit} disabled={loading}>
            {loading ? "Saving…" : actionLabels[action]}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Batches Panel ----
function BatchesPanel({ token }) {
  const [batches, setBatches] = useState([]);

  useEffect(() => {
    apiFetch("/emissions/batches/", token).then((d) => setBatches(d.results || []));
  }, [token]);

  const statusColor = { completed: "#2a9d8f", failed: "#e76f51", processing: "#e9c46a", pending: "#888" };

  return (
    <div style={styles.section}>
      <h3 style={styles.sectionTitle}>Ingestion History</h3>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Source</th>
            <th style={styles.th}>File</th>
            <th style={styles.th}>Date</th>
            <th style={styles.th}>Accepted</th>
            <th style={styles.th}>Rejected</th>
            <th style={styles.th}>Status</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id} style={styles.row}>
              <td style={styles.td}>{b.source_type.replace(/_/g, " ")}</td>
              <td style={styles.tdSmall}>{b.original_filename}</td>
              <td style={styles.td}>{new Date(b.uploaded_at).toLocaleDateString()}</td>
              <td style={styles.td}>{b.row_count_accepted}</td>
              <td style={styles.td}>{b.row_count_rejected}</td>
              <td style={styles.td}><span style={{ ...styles.badge, background: statusColor[b.status] }}>{b.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- Main App ----
export default function App() {
  const { token, user, login, logout } = useAuth();
  const [summary, setSummary] = useState(null);
  const [activeView, setActiveView] = useState("dashboard");
  const [reviewState, setReviewState] = useState(null); // {record, action, reload}

  const loadSummary = useCallback(() => {
    if (token) apiFetch("/emissions/dashboard/", token).then(setSummary).catch(console.error);
  }, [token]);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  if (!token) return <LoginScreen onLogin={login} />;

  const navItems = [
    { id: "dashboard", label: "📊 Dashboard" },
    { id: "records", label: "📋 Records" },
    { id: "ingest", label: "⬆️ Ingest" },
    { id: "batches", label: "🗂 Batches" },
  ];

  return (
    <div style={styles.app}>
      <nav style={styles.nav}>
        <div style={styles.navBrand}>
          <span style={styles.logoLeaf}>🌿</span>
          <span style={styles.navTitle}>Breathe ESG</span>
        </div>
        <div style={styles.navLinks}>
          {navItems.map((n) => (
            <button key={n.id} style={activeView === n.id ? styles.navLinkActive : styles.navLink} onClick={() => setActiveView(n.id)}>
              {n.label}
            </button>
          ))}
        </div>
        <div style={styles.navUser}>
          <span style={{ color: "#aaa", fontSize: 13 }}>{user?.username} · {user?.organisation}</span>
          <button style={styles.navLogout} onClick={logout}>Sign out</button>
        </div>
      </nav>

      <main style={styles.main}>
        {activeView === "dashboard" && (
          <>
            <h2 style={styles.pageTitle}>Emissions Overview</h2>
            <SummaryCards summary={summary} />
            <CategoryBreakdown summary={summary} />
          </>
        )}
        {activeView === "records" && (
          <RecordTable
            token={token}
            onReview={(record, action, reload) => setReviewState({ record, action, reload })}
          />
        )}
        {activeView === "ingest" && (
          <IngestPanel token={token} onDone={loadSummary} />
        )}
        {activeView === "batches" && <BatchesPanel token={token} />}
      </main>

      {reviewState && (
        <ReviewModal
          record={reviewState.record}
          action={reviewState.action}
          token={token}
          onClose={() => setReviewState(null)}
          onDone={() => { reviewState.reload(); loadSummary(); }}
        />
      )}
    </div>
  );
}

// ---- Styles ----
const styles = {
  app: { minHeight: "100vh", background: "#0f1117", color: "#e2e8f0", fontFamily: "'IBM Plex Mono', 'Fira Code', monospace" },
  nav: { display: "flex", alignItems: "center", gap: 16, padding: "12px 24px", background: "#161b22", borderBottom: "1px solid #30363d" },
  navBrand: { display: "flex", alignItems: "center", gap: 8, marginRight: 16 },
  navTitle: { fontSize: 16, fontWeight: 700, color: "#52b788", letterSpacing: "-0.5px" },
  logoLeaf: { fontSize: 20 },
  navLinks: { display: "flex", gap: 4, flex: 1 },
  navLink: { background: "none", border: "none", color: "#8b949e", padding: "6px 12px", cursor: "pointer", borderRadius: 6, fontSize: 13 },
  navLinkActive: { background: "#21262d", border: "none", color: "#52b788", padding: "6px 12px", cursor: "pointer", borderRadius: 6, fontSize: 13 },
  navUser: { display: "flex", alignItems: "center", gap: 12 },
  navLogout: { background: "none", border: "1px solid #30363d", color: "#8b949e", padding: "4px 10px", cursor: "pointer", borderRadius: 4, fontSize: 12 },
  main: { padding: "24px 32px", maxWidth: 1400, margin: "0 auto" },
  pageTitle: { fontSize: 22, fontWeight: 700, color: "#e2e8f0", marginBottom: 20 },

  loginWrap: { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0f1117" },
  loginCard: { background: "#161b22", border: "1px solid #30363d", borderRadius: 12, padding: 40, width: 360 },
  loginLogo: { textAlign: "center", marginBottom: 28 },
  loginTitle: { color: "#52b788", fontSize: 24, margin: "8px 0 4px" },
  loginSub: { color: "#8b949e", fontSize: 13 },
  loginHint: { color: "#555", fontSize: 12, textAlign: "center", marginTop: 16 },

  input: { width: "100%", padding: "10px 12px", background: "#0f1117", border: "1px solid #30363d", borderRadius: 6, color: "#e2e8f0", fontSize: 14, marginBottom: 12, boxSizing: "border-box" },
  error: { color: "#e76f51", fontSize: 13, marginBottom: 8 },
  btnPrimary: { width: "100%", padding: "10px", background: "#2d6a4f", border: "none", borderRadius: 6, color: "#fff", fontSize: 14, cursor: "pointer", fontWeight: 600 },

  cardGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 24 },
  card: { borderRadius: 10, padding: "16px", },
  cardValue: { fontSize: 22, fontWeight: 700 },
  cardLabel: { fontSize: 12, marginTop: 4 },

  section: { background: "#161b22", border: "1px solid #30363d", borderRadius: 10, padding: 20, marginBottom: 24 },
  sectionTitle: { color: "#e2e8f0", fontSize: 16, fontWeight: 600, marginBottom: 16, marginTop: 0 },

  barRow: { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 },
  barLabel: { width: 200, fontSize: 12, color: "#aaa", display: "flex", alignItems: "center", gap: 6 },
  barTrack: { flex: 1, height: 8, background: "#21262d", borderRadius: 4, overflow: "hidden" },
  barFill: { height: "100%", borderRadius: 4, transition: "width 0.3s ease" },
  barValue: { width: 80, fontSize: 12, color: "#aaa", textAlign: "right" },

  tableHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 },
  filters: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" },
  select: { padding: "5px 8px", background: "#0f1117", border: "1px solid #30363d", color: "#e2e8f0", borderRadius: 4, fontSize: 12 },
  btnSmall: { padding: "5px 10px", background: "#2d6a4f", border: "none", color: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 12 },

  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: { textAlign: "left", padding: "8px 10px", color: "#8b949e", fontWeight: 600, borderBottom: "1px solid #30363d", whiteSpace: "nowrap" },
  td: { padding: "8px 10px", borderBottom: "1px solid #21262d", color: "#e2e8f0" },
  tdSmall: { padding: "8px 10px", borderBottom: "1px solid #21262d", color: "#8b949e", fontSize: 11, maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  row: { background: "transparent" },
  flaggedRow: { background: "rgba(231, 111, 81, 0.06)" },

  badge: { padding: "2px 8px", borderRadius: 12, fontSize: 11, color: "#fff", fontWeight: 600 },
  scopeBadge: (s) => ({
    display: "inline-block", padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 700,
    background: s === 1 ? "#2d6a4f" : s === 2 ? "#40916c" : "#1a472a", color: "#fff"
  }),

  btnXs: (color) => ({ padding: "2px 7px", background: color, border: "none", borderRadius: 3, color: "#fff", cursor: "pointer", fontSize: 12, marginRight: 4 }),

  pagination: { display: "flex", alignItems: "center", gap: 12, marginTop: 16, justifyContent: "flex-end" },
  pageBtn: { padding: "4px 10px", background: "#21262d", border: "1px solid #30363d", color: "#e2e8f0", borderRadius: 4, cursor: "pointer", fontSize: 12 },

  tabs: { display: "flex", gap: 4, marginBottom: 12 },
  tab: { padding: "6px 14px", background: "#0f1117", border: "1px solid #30363d", color: "#8b949e", borderRadius: 4, cursor: "pointer", fontSize: 13 },
  tabActive: { padding: "6px 14px", background: "#2d6a4f", border: "1px solid #2d6a4f", color: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 13 },
  fileInput: { display: "block", marginBottom: 12, color: "#aaa", fontSize: 13 },
  successBox: { marginTop: 12, padding: 12, background: "#1a3a2a", border: "1px solid #2d6a4f", borderRadius: 6, color: "#52b788", fontSize: 13 },
  errorBox: { marginTop: 12, padding: 12, background: "#3a1a1a", border: "1px solid #e76f51", borderRadius: 6, color: "#e76f51", fontSize: 13 },

  loading: { color: "#8b949e", padding: 20, textAlign: "center" },

  modalOverlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 },
  modal: { background: "#161b22", border: "1px solid #30363d", borderRadius: 10, padding: 28, width: 420, maxWidth: "90vw" },
  flagWarning: { background: "rgba(231,111,81,0.1)", border: "1px solid #e76f51", borderRadius: 6, padding: 10, color: "#e76f51", fontSize: 12, margin: "12px 0" },
  textarea: { width: "100%", minHeight: 80, padding: 10, background: "#0f1117", border: "1px solid #30363d", borderRadius: 6, color: "#e2e8f0", fontSize: 13, marginTop: 12, boxSizing: "border-box", resize: "vertical" },
  modalActions: { display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 16 },
  btnCancel: { padding: "8px 16px", background: "none", border: "1px solid #30363d", color: "#8b949e", borderRadius: 6, cursor: "pointer" },
};
