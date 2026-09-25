import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Tile } from "../components/ui";
import { dateTime, ngn } from "../format";
import type { Campaign } from "../types";
import { CAMPAIGN_STATUS } from "./Campaigns";

interface Recipient {
  contact_id: number; name: string; phone: string | null; email: string | null; status: string;
  error: string; replied: boolean; sent_at: string | null; read_at: string | null;
}

export default function CampaignDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [c, setC] = useState<Campaign | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Campaign>(`/campaigns/${id}`).then(setC).catch((e) => setError(e.message));
    api.get<Recipient[]>(`/campaigns/${id}/recipients${filter ? `?status=${filter}` : ""}`).then(setRecipients).catch(() => {});
  }, [id, filter]);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  async function act(path: string) {
    try {
      const r = await api.post<Campaign>(`/campaigns/${id}/${path}`);
      if (path === "duplicate") nav(`/campaigns/${r.id}/edit`);
      else load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (error && !c) return <p className="error">{error}</p>;
  if (!c) return <p className="muted">Loading…</p>;
  const r = c.report;
  const pct = (n: number) => (r.sent ? ` (${Math.round((n / r.sent) * 100)}%)` : "");

  return (
    <>
      <div className="topline">
        <div>
          <p className="muted"><Link to="/campaigns">Campaigns</Link> /</p>
          <h1>{c.name}</h1>
          <div className="row" style={{ marginTop: 6 }}>
            <span className={`pill cs-${c.status}`}>{CAMPAIGN_STATUS[c.status]}</span>
            <span className="muted">
              {c.channel === "whatsapp" ? "WhatsApp" : "Email"} · {c.category}
              {c.status === "scheduled" ? ` · sends ${dateTime(c.scheduled_at)}` : c.started_at ? ` · started ${dateTime(c.started_at)}` : ""}
            </span>
            {c.test_mode && <span className="chip">test mode: nothing was really sent</span>}
          </div>
        </div>
        <div className="row">
          {(c.status === "scheduled" || c.status === "sending") && <button className="danger" onClick={() => act("cancel")}>Cancel campaign</button>}
          {c.status === "scheduled" && <Link className="btn" to={`/campaigns/${c.id}/edit`}>Edit</Link>}
          <button onClick={() => act("duplicate")}>Duplicate</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="tiles">
        <Tile label={c.status === "scheduled" ? "Will receive" : "Sent"} value={(c.status === "scheduled" ? c.audience?.will_receive ?? 0 : r.sent).toLocaleString()} accent />
        <Tile label="Delivered" value={`${r.delivered}${pct(r.delivered)}`} />
        <Tile label="Read" value={`${r.read}${pct(r.read)}`} />
        <Tile label="Replied" value={`${r.replied}${pct(r.replied)}`} />
        <Tile label="Failed / skipped" value={`${r.failed} / ${r.skipped}`} />
        <Tile label="Est. Meta fees" value={ngn(r.estimated_cost_ngn)} />
      </div>
      {r.queued > 0 && <p className="muted" style={{ marginBottom: 12 }}>{r.queued} messages still in the queue. They go out at a safe pace to protect KGL's WhatsApp number.</p>}

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Message</h2>
        {c.wa_template_name && <p className="muted">Template: <span className="mono">{c.wa_template_name}</span> ({c.wa_template_lang}) · variables: {c.wa_template_params.join(", ") || "none"}</p>}
        {c.media_url && <p className="muted">Attachment ({c.media_type}): <a href={c.media_url} target="_blank" rel="noreferrer">{c.media_url}</a></p>}
        <p style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{c.body}</p>
      </div>

      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h2>Recipients</h2>
        <select id="rec-filter" style={{ width: "auto" }} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter recipients">
          <option value="">Everyone</option>
          {["queued", "sent", "delivered", "read", "failed", "skipped"].map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Customer</th><th>Contact</th><th>Status</th><th>Replied</th><th>Sent</th><th>Read</th><th>Problem</th></tr></thead>
          <tbody>
            {recipients.map((x) => (
              <tr key={x.contact_id}>
                <td><Link to={`/customers/${x.contact_id}`}>{x.name || "Unnamed"}</Link></td>
                <td className="mono">{x.phone ?? x.email}</td>
                <td>{x.status}</td>
                <td>{x.replied ? "Yes" : ""}</td>
                <td>{dateTime(x.sent_at)}</td>
                <td>{dateTime(x.read_at)}</td>
                <td className="error">{x.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {recipients.length === 0 && <div className="empty">{c.status === "scheduled" ? "Recipients are picked when the campaign starts." : "No recipients in this view."}</div>}
      </div>
    </>
  );
}
