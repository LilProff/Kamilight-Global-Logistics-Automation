import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { dateTime, ngn } from "../format";
import type { Campaign } from "../types";

export const CAMPAIGN_STATUS: Record<Campaign["status"], string> = {
  draft: "Draft", scheduled: "Scheduled", sending: "Sending", sent: "Sent", cancelled: "Cancelled",
};

export default function Campaigns() {
  const nav = useNavigate();
  const [items, setItems] = useState<Campaign[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () => api.get<Campaign[]>("/campaigns").then(setItems).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 5000);  // live progress while campaigns send
    return () => clearInterval(t);
  }, []);

  return (
    <>
      <div className="topline">
        <h1>Campaigns</h1>
        <Link className="btn primary" to="/campaigns/new">New campaign</Link>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Campaign</th><th>Status</th><th>Channel</th><th>When</th>
              <th className="right">Sent</th><th className="right">Read</th><th className="right">Replies</th><th className="right">Failed</th><th className="right">Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((c) => (
              <tr key={c.id} className="link" onClick={() => nav(c.status === "draft" ? `/campaigns/${c.id}/edit` : `/campaigns/${c.id}`)}>
                <td><b>{c.name}</b>{c.test_mode && <span className="chip" style={{ marginLeft: 6 }}>test mode</span>}</td>
                <td><span className={`pill cs-${c.status}`}>{CAMPAIGN_STATUS[c.status]}</span></td>
                <td>{c.channel === "whatsapp" ? "WhatsApp" : "Email"} · {c.category}</td>
                <td>{dateTime(c.started_at ?? c.scheduled_at ?? c.created_at)}</td>
                <td className="right num">{c.report.sent}</td>
                <td className="right num">{c.report.read}</td>
                <td className="right num">{c.report.replied}</td>
                <td className="right num">{c.report.failed}</td>
                <td className="right num">{ngn(c.report.estimated_cost_ngn)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {items?.length === 0 && <div className="empty">No campaigns yet. <Link to="/campaigns/new">Create the first one</Link>.</div>}
      </div>
    </>
  );
}
