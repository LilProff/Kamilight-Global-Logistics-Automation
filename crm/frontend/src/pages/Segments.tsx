import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { routeLabel, STATUS_LABEL, TYPE_LABEL } from "../format";
import type { Filters, Segment } from "../types";
import { customersLink } from "./Dashboard";

export function describe(f: Filters): string {
  const parts: string[] = [];
  if (f.statuses?.length) parts.push(f.statuses.map((s) => STATUS_LABEL[s]).join(" or "));
  if (f.customer_types?.length) parts.push(f.customer_types.map((t) => TYPE_LABEL[t]).join(" or "));
  if (f.routes_any?.length) parts.push("route " + f.routes_any.map(routeLabel).join(" / "));
  if (f.not_shipped_for_days) parts.push(`no shipment in ${f.not_shipped_for_days}+ days`);
  if (f.shipped_within_days) parts.push(`shipped in last ${f.shipped_within_days} days`);
  if (f.min_shipments) parts.push(`${f.min_shipments}+ shipments`);
  if (f.min_spend) parts.push(`spent ₦${Number(f.min_spend).toLocaleString()}+`);
  if (f.cities?.length) parts.push("in " + f.cities.join(", "));
  if (f.tags_any?.length) parts.push("tagged " + f.tags_any.join(", "));
  if (f.never_shipped) parts.push("never shipped");
  if (f.opted_in_only) parts.push("opted in");
  if (f.search) parts.push(`matching "${f.search}"`);
  return parts.join(" · ") || "All customers";
}

export default function Segments() {
  const [items, setItems] = useState<Segment[] | null>(null);
  const [error, setError] = useState("");
  const load = () => api.get<Segment[]>("/segments").then(setItems).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function remove(s: Segment) {
    await api.del(`/segments/${s.id}`);
    load();
  }

  return (
    <>
      <div className="topline">
        <h1>Segments</h1>
        <Link className="btn" to="/customers">Build a new segment from Customers</Link>
      </div>
      <p className="muted" style={{ marginBottom: 14 }}>Saved filters. Counts update as customers change, so each segment is always ready for a campaign.</p>
      {error && <p className="error">{error}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Segment</th><th>Who's in it</th><th className="right">Customers</th><th /></tr></thead>
          <tbody>
            {items?.map((s) => (
              <tr key={s.id}>
                <td><b>{s.name}</b>{s.description && <div className="muted" style={{ fontSize: 12 }}>{s.description}</div>}</td>
                <td className="muted">{describe(s.filters)}</td>
                <td className="right num">{s.count.toLocaleString()}</td>
                <td className="right">
                  <div className="row" style={{ justifyContent: "flex-end" }}>
                    <Link className="btn" to={customersLink(s.filters)}>View</Link>
                    <Link className="btn primary" to={`/campaigns/new?segment=${s.id}`}>Message</Link>
                    <button className="ghost danger" onClick={() => remove(s)} aria-label={`Delete ${s.name}`}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items?.length === 0 && <div className="empty">No segments yet. Filter your customers, then choose "Save as segment".</div>}
      </div>
    </>
  );
}
