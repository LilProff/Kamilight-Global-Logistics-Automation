import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { STATUS_LABEL } from "../format";
import { Tile } from "../components/ui";
import type { Stats, Status } from "../types";

const ORDER: Status[] = ["new", "quoted", "booked", "repeat", "vip", "dormant", "lost"];

export const customersLink = (filters: object) => `/customers?f=${encodeURIComponent(JSON.stringify(filters))}`;

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get<Stats>("/stats").then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!stats) return <p className="muted">Loading…</p>;
  const max = Math.max(1, ...ORDER.map((s) => stats.by_status[s] ?? 0));

  return (
    <>
      <div className="topline">
        <h1>Dashboard</h1>
        <div className="row">
          <Link className="btn" to="/customers">Customers</Link>
          <Link className="btn primary" to="/campaigns/new">New campaign</Link>
        </div>
      </div>
      <div className="tiles">
        <Tile label="Customers" value={stats.total.toLocaleString()} accent />
        <Tile label="Agreed to WhatsApp marketing" value={stats.marketing_consent.toLocaleString()} />
        <Tile label="New in last 30 days" value={stats.new_last_30d.toLocaleString()} />
        <Tile label="Messages sent (30 days)" value={stats.messages_sent_30d.toLocaleString()} />
        <Tile label="Replies (30 days)" value={stats.replies_30d.toLocaleString()} />
      </div>
      <div className="card">
        <h2>Customers by status</h2>
        <div className="stack" style={{ gap: 8 }}>
          {ORDER.map((s) => {
            const n = stats.by_status[s] ?? 0;
            return (
              <Link key={s} to={customersLink({ statuses: [s] })} style={{ color: "inherit", textDecoration: "none" }}>
                <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 60px", gap: 10, alignItems: "center" }}>
                  <span>{STATUS_LABEL[s]}</span>
                  <div style={{ background: "var(--rule-2)", borderRadius: 4, height: 12 }}>
                    <div style={{ width: `${(n / max) * 100}%`, background: s === "dormant" ? "var(--accent)" : "var(--steel)", height: 12, borderRadius: 4 }} />
                  </div>
                  <span className="num" style={{ textAlign: "right" }}>{n.toLocaleString()}</span>
                </div>
              </Link>
            );
          })}
        </div>
        {(stats.by_status.dormant ?? 0) > 0 && (
          <p style={{ marginTop: 14 }}>
            <b>{stats.by_status.dormant} dormant customers</b> haven't shipped in 60+ days.{" "}
            <Link to={`/campaigns/new?f=${encodeURIComponent(JSON.stringify({ statuses: ["dormant"] }))}`}>Send them a win-back campaign →</Link>
          </p>
        )}
      </div>
    </>
  );
}
