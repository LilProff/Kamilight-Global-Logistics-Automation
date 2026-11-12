import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { dateTime } from "../format";
import type { ChatDetail, ChatRow } from "../types";

type View = "all" | "needs_human" | "unread";
const VIEWS: [View, string][] = [["all", "All"], ["needs_human", "Needs a person"], ["unread", "Unread"]];
const WHO: Record<string, string> = { customer: "Customer", ai: "AI assistant", staff: "KGL team" };

export default function Inbox() {
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get("c")) || null;
  const [view, setView] = useState<View>("all");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<ChatRow[] | null>(null);
  const [error, setError] = useState("");

  const loadList = useCallback(() => {
    api.get<ChatRow[]>(`/inbox?view=${view}&q=${encodeURIComponent(q)}`).then(setRows).catch((e) => setError(e.message));
  }, [view, q]);
  useEffect(() => {
    loadList();
    const t = setInterval(loadList, 5000);
    return () => clearInterval(t);
  }, [loadList]);

  const open = (id: number) => setParams({ c: String(id) });

  return (
    <>
      <div className="topline">
        <h1>Inbox</h1>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="inbox">
        <section className="card inbox-list" aria-label="Conversations">
          <div className="steps" role="tablist">
            {VIEWS.map(([v, label]) => (
              <button key={v} role="tab" aria-selected={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{label}</button>
            ))}
          </div>
          <input aria-label="Search conversations" placeholder="Search name or number" value={q} onChange={(e) => setQ(e.target.value)} />
          <ul className="chat-list">
            {rows?.map((r) => (
              <li key={r.contact_id}>
                <button className={`chat-row ${selected === r.contact_id ? "sel" : ""}`} onClick={() => open(r.contact_id)}>
                  <span className="row" style={{ justifyContent: "space-between", width: "100%", gap: 6 }}>
                    <b>{r.name || r.phone || "Unknown"}</b>
                    <span className="muted" style={{ fontSize: 11.5 }}>{dateTime(r.last_message_at)}</span>
                  </span>
                  <span className="muted preview">{r.preview || "—"}</span>
                  <span>
                    {r.needs_human && <span className="pill st-vip">Needs a person</span>}{" "}
                    {r.unread && <span className="pill st-new">Unread</span>}{" "}
                    {r.ai_paused && <span className="pill st-dormant">AI paused</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {rows && !rows.length && (
            <p className="empty">
              {view === "all" && !q ? "No WhatsApp conversations yet. They'll appear here as soon as someone messages KGL's number." : "Nothing here."}
            </p>
          )}
        </section>
        {selected ? <Thread key={selected} id={selected} onChanged={loadList} /> : (
          <section className="card inbox-thread"><p className="empty">Pick a conversation to read it and reply.</p></section>
        )}
      </div>
    </>
  );
}

function Thread({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    api.get<ChatDetail>(`/inbox/${id}`).then(setChat).catch((e) => setError(e.message));
  }, [id]);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [chat?.messages.length]);

  async function act(fn: () => Promise<unknown>) {
    setError("");
    setBusy(true);
    try {
      await fn();
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const send = () => act(async () => { await api.post(`/inbox/${id}/reply`, { text }); setText(""); });

  if (!chat) return <section className="card inbox-thread"><p className="muted">{error || "Loading…"}</p></section>;
  const blocked = chat.do_not_contact ? "This customer asked not to be messaged." : !chat.window_open ? "More than 24 hours since they last wrote. WhatsApp only allows an approved template now (send one from Campaigns)." : "";

  return (
    <section className="card inbox-thread" aria-label="Conversation">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ marginBottom: 2 }}>{chat.name || chat.phone}</h2>
          <p className="muted"><span className="mono">{chat.phone}</span> · <Link to={`/customers/${chat.contact_id}`}>Open customer profile</Link></p>
        </div>
        <div className="row">
          {chat.ai_paused
            ? <button disabled={busy} onClick={() => act(() => api.post(`/inbox/${id}/ai`, { paused: false }))}>Hand back to AI</button>
            : <button disabled={busy} onClick={() => act(() => api.post(`/inbox/${id}/ai`, { paused: true }))}>Pause AI</button>}
          {chat.needs_human && <button disabled={busy} onClick={() => act(() => api.post(`/inbox/${id}/resolve`))}>Mark as handled</button>}
        </div>
      </div>
      {chat.needs_human && <p className="banner" style={{ margin: "12px 0 0" }}><b>Needs a person:</b> {chat.handoff_reason || "The AI asked for help."}</p>}

      <div className="msgs" role="log" aria-live="polite">
        {chat.messages.map((m) => (
          <div key={m.id} className={`msg ${m.direction}`}>
            <div className="msg-body">{m.body}</div>
            <div className="msg-meta">
              {WHO[m.sender]}{m.sender === "staff" && m.staff_email ? ` (${m.staff_email})` : ""} · {dateTime(m.at)}
              {m.error && <span className="error"> · not delivered: {m.error}</span>}
            </div>
          </div>
        ))}
        {!chat.messages.length && <p className="empty">No messages yet.</p>}
        <div ref={end} />
      </div>

      {error && <p className="error" role="alert">{error}</p>}
      {blocked ? <p className="muted">{blocked}</p> : (
        <form className="reply" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(); }}>
          <label className="field" style={{ flex: 1 }}>Reply
            <textarea id="reply-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a reply. Sending it pauses the AI for this chat." />
          </label>
          <button className="primary" type="submit" disabled={busy || !text.trim()}>Send</button>
        </form>
      )}
    </section>
  );
}
