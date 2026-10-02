import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, cleanFilters } from "../api";
import FilterBuilder, { refreshOptions } from "../components/FilterBuilder";
import { Dialog, StatusPill } from "../components/ui";
import { daysAgo, ngn, routeLabel, TYPE_LABEL } from "../format";
import type { Contact, CustomerType, Filters } from "../types";

interface Page { items: Contact[]; total: number; page: number; page_size: number }

function parseFilters(raw: string | null): Filters {
  try {
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export default function Customers() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => parseFilters(params.get("f")));
  const [search, setSearch] = useState(filters.search ?? "");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("recent");
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [showFilters, setShowFilters] = useState(Object.keys(filters).length > 0);
  const [dialog, setDialog] = useState<"" | "add" | "import" | "segment">("");

  const effective = cleanFilters({ ...filters, search });

  const load = useCallback(() => {
    api
      .post<Page>("/contacts/search", { filters: effective, page, page_size: 50, sort })
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(e.message));
  }, [JSON.stringify(effective), page, sort]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    const f = cleanFilters(filters);
    setParams(Object.keys(f).length ? { f: JSON.stringify(f) } : {}, { replace: true });
    setPage(1);
  }, [JSON.stringify(filters)]);

  async function exportCsv() {
    const blob = await api.post<Blob>("/contacts/export", { filters: effective });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: "kgl-customers.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  const filterCount = Object.keys(cleanFilters(filters)).length;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <div className="topline">
        <h1>Customers</h1>
        <div className="row">
          <button onClick={() => setDialog("import")}>Import list</button>
          <button onClick={() => setDialog("add")}>Add customer</button>
          <button className="primary" onClick={() => nav(`/campaigns/new?f=${encodeURIComponent(JSON.stringify(effective))}`)}>
            Message these customers
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row">
          <input
            id="search"
            style={{ flex: "1 1 240px", width: "auto" }}
            placeholder="Search name, phone, email or company"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
          <button onClick={() => setShowFilters(!showFilters)} aria-expanded={showFilters}>
            Filters{filterCount ? ` (${filterCount})` : ""}
          </button>
          {filterCount > 0 && <button className="ghost" onClick={() => setFilters({})}>Clear</button>}
          <select id="sort" style={{ width: "auto" }} value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
            <option value="recent">Recently updated</option>
            <option value="name">Name</option>
            <option value="spend">Highest spend</option>
            <option value="last_shipment">Last shipment</option>
            <option value="created">Newest</option>
          </select>
        </div>
        {showFilters && (
          <div style={{ marginTop: 14 }}>
            <FilterBuilder value={filters} onChange={setFilters} />
          </div>
        )}
      </div>

      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <span className="muted">{data ? `${data.total.toLocaleString()} customer${data.total === 1 ? "" : "s"}` : "Loading…"}</span>
        <div className="row">
          <button className="ghost" onClick={() => setDialog("segment")} disabled={!filterCount && !search}>Save as segment</button>
          <button className="ghost" onClick={exportCsv}>Export CSV</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th><th>WhatsApp</th><th>Status</th><th>Type</th><th>Routes</th>
              <th className="right">Shipments</th><th className="right">Spend</th><th>Last shipment</th><th>Consent</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className="link" onClick={() => nav(`/customers/${c.id}`)}>
                <td>
                  <Link to={`/customers/${c.id}`} onClick={(e) => e.stopPropagation()}><b>{c.name || "Unnamed"}</b></Link>
                  {c.company && <div className="muted" style={{ fontSize: 12 }}>{c.company}</div>}
                </td>
                <td className="mono">
                  {c.phone ?? (c.email ? <span className="muted">{c.email}</span> : <span className="pill st-quoted">Needs a number</span>)}
                </td>
                <td><StatusPill status={c.status} /></td>
                <td>{TYPE_LABEL[c.customer_type]}</td>
                <td>{c.routes.map((r) => <span key={r} className="chip">{routeLabel(r)}</span>)}</td>
                <td className="right num">{c.shipments_count}</td>
                <td className="right num">{ngn(c.total_spend_ngn)}</td>
                <td>{daysAgo(c.last_shipment_at)}</td>
                <td>
                  {c.do_not_contact ? <span className="pill st-lost">Do not contact</span>
                    : c.wa_opted_out ? <span className="pill st-lost">Replied STOP</span>
                    : c.wa_opt_in ? <span className="pill st-booked">Opted in</span>
                    : <span className="pill st-dormant">No consent</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && (
          <div className="empty">
            {data.total === 0 && !filterCount && !search
              ? <>No customers yet. <button onClick={() => setDialog("import")}>Import KGL's customer list</button></>
              : "No customers match these filters."}
          </div>
        )}
      </div>

      {pages > 1 && (
        <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="muted">Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {dialog === "add" && <AddCustomer onClose={() => setDialog("")} onSaved={(id) => nav(`/customers/${id}`)} />}
      {dialog === "import" && <ImportDialog onClose={() => { setDialog(""); refreshOptions(); load(); }} />}
      {dialog === "segment" && <SaveSegment filters={effective} onClose={() => setDialog("")} />}
    </>
  );
}

function AddCustomer({ onClose, onSaved }: { onClose: () => void; onSaved: (id: number) => void }) {
  const [form, setForm] = useState({ name: "", phone: "", email: "", city: "", customer_type: "individual" as CustomerType, wa_opt_in: false });
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const c = await api.post<Contact>("/contacts", { ...form, email: form.email || null, phone: form.phone || null, source: "manual" });
      refreshOptions();
      onSaved(c.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Dialog title="Add customer" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">Name<input id="add-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <div className="grid2">
          <label className="field">WhatsApp number<input id="add-phone" placeholder="0801 234 5678" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <label className="field">Email<input id="add-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label className="field">City<input id="add-city" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
          <label className="field">Customer type
            <select id="add-type" value={form.customer_type} onChange={(e) => setForm({ ...form, customer_type: e.target.value as CustomerType })}>
              {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        <label className="check">
          <input type="checkbox" checked={form.wa_opt_in} onChange={(e) => setForm({ ...form, wa_opt_in: e.target.checked })} />
          The customer agreed to receive WhatsApp offers and updates from KGL
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row"><button className="primary">Add customer</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}

interface ImportResult { rows: number; created: number; updated: number; skipped: number; needs_fix: number; problems: string[] }

function ImportDialog({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [optIn, setOptIn] = useState(false);
  const [type, setType] = useState("");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("opt_in", String(optIn));
    body.append("customer_type", type);
    body.append("extra_tag", tag);
    try {
      setResult(await api.post<ImportResult>("/contacts/import", body));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Import customers" onClose={onClose}>
      {result ? (
        <div className="stack">
          <p className="ok"><b>{result.created}</b> new customers added, <b>{result.updated}</b> existing ones updated.</p>
          {result.skipped > 0 && <p><b>{result.skipped}</b> repeated rows were folded into the first one (nothing lost).</p>}
          {result.needs_fix > 0 && (
            <p>
              <b>{result.needs_fix}</b> customers were kept but have no usable WhatsApp number. They're tagged <span className="chip">fix-phone</span> with the number as it
              appeared in the sheet saved in their notes, so you can correct them.{" "}
              <a href={`/customers?f=${encodeURIComponent(JSON.stringify({ tags_any: ["fix-phone"] }))}`}>Show them</a>
            </p>
          )}
          {result.problems.length > 0 && (
            <details><summary>Show problems ({result.problems.length})</summary><ul>{result.problems.map((p) => <li key={p}>{p}</li>)}</ul></details>
          )}
          <button className="primary" onClick={onClose}>Done</button>
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          <p className="muted">
            Excel (.xlsx) or CSV. Columns are matched automatically (Name, Phone/WhatsApp, Email, Company, City, Tag). Phone numbers
            are cleaned and duplicates merged, so importing the same list twice is safe.
          </p>
          <input id="import-file" type="file" accept=".xlsx,.xlsm,.csv" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="grid2">
            <label className="field">Customer type (optional)
              <select id="import-type" value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">Work it out per row</option>
                {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="field">Add a tag (optional)<input id="import-tag" placeholder="e.g. 2025 list" value={tag} onChange={(e) => setTag(e.target.value)} /></label>
          </div>
          <label className="check">
            <input type="checkbox" checked={optIn} onChange={(e) => setOptIn(e.target.checked)} />
            <span>These customers agreed to receive WhatsApp offers from KGL. <span className="muted">Only tick this if it's true: Meta can restrict KGL's number if people report unwanted marketing.</span></span>
          </label>
          {error && <p className="error">{error}</p>}
          <div className="row"><button className="primary" disabled={busy || !file}>{busy ? "Importing…" : "Import"}</button><button type="button" onClick={onClose}>Cancel</button></div>
        </form>
      )}
    </Dialog>
  );
}

function SaveSegment({ filters, onClose }: { filters: Filters; onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post("/segments", { name, description, filters });
      nav("/segments");
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Dialog title="Save as segment" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <p className="muted">A segment is a saved filter. It updates itself as customers change, so it's always ready for the next campaign.</p>
        <label className="field">Name<input id="segment-name" required placeholder="e.g. China importers, dormant 60+ days" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">Description (optional)<input id="segment-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="row"><button className="primary">Save segment</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}
