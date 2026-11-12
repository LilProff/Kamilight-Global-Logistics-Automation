import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api";
import type { AiSettingsView, Me } from "../types";

const STARTER = `ABOUT KGL
Kamilight Global Logistics is a freight forwarder based in Lagos, Nigeria.

SERVICES WE OFFER
- Import from China by air and by sea (to Lagos)
- Import from the UK and the US
- Export / shipping from Lagos to the UK, US and Canada
- Customs clearing and haulage

HOW TO BOOK
(Describe the steps: e.g. send route, goods and weight on WhatsApp, we confirm price, then drop-off or pickup.)

OFFICE AND HOURS
(Address, opening hours, phone.)

PAYMENT
(Accepted methods, when payment is due.)

PRICES AND TRANSIT TIMES
(Only add rates or timelines here that you are happy for the AI to quote word for word. Anything not listed here is passed to your team.)

ITEMS WE DO NOT HANDLE
(Prohibited or restricted goods.)`;

interface Turn { role: "user" | "assistant"; content: string; actions?: string[]; handoff?: string }

export default function AiAssistant() {
  const { me } = useOutletContext<{ me: Me }>();
  const canEdit = me.role === "admin";
  const [s, setS] = useState<AiSettingsView | null>(null);
  const [form, setForm] = useState({ knowledge: "", extra_instructions: "", max_replies_per_day: 12 });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    api.get<AiSettingsView>("/ai/settings").then((v) => {
      setS(v);
      setForm({ knowledge: v.knowledge, extra_instructions: v.extra_instructions, max_replies_per_day: v.max_replies_per_day });
    }).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function save(enabled: boolean) {
    setError("");
    try {
      const v = await api.put<AiSettingsView>("/ai/settings", { enabled, ...form, max_replies_per_day: Number(form.max_replies_per_day) });
      setS(v);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!s) return <p className="muted">{error || "Loading…"}</p>;
  return (
    <>
      <div className="topline">
        <h1>AI assistant</h1>
        <div className="row">
          <span className={`pill ${s.enabled ? "cs-sent" : "cs-draft"}`}>{s.enabled ? "On" : "Off"}</span>
          {canEdit && (s.enabled
            ? <button onClick={() => save(false)}>Switch off</button>
            : <button className="primary" onClick={() => save(true)}>Switch on</button>)}
        </div>
      </div>
      <p className="muted" style={{ marginBottom: 16, maxWidth: "72ch" }}>
        Answers customers on WhatsApp the moment they write, saves what they tell it onto their record, logs quote requests, and hands the chat
        to your team when a person is needed. It only states facts you write below, never invents prices, and stays quiet once a staff member replies.
      </p>
      {!s.configured && <p className="banner" role="status"><b>Not connected.</b> Add the <span className="mono">ANTHROPIC_API_KEY</span> setting in Render to switch the AI on. You can still prepare the knowledge below.</p>}
      {!canEdit && <p className="banner">Only an administrator can change the AI's settings. You can still try it below.</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <div className="tiles">
        <div className="tile"><div className="k">AI replies, last 24h</div><div className="v">{s.ai_replies_24h}</div></div>
        <div className="tile"><div className="k">Waiting for your team</div><div className="v">{s.waiting_for_staff}</div></div>
        <div className="tile"><div className="k">Model</div><div className="v mono" style={{ fontSize: 14, paddingTop: 10 }}>{s.model}</div></div>
      </div>

      <div className="builder wide">
        <section className="card stack" aria-label="What the AI knows">
          <h2>What the AI knows</h2>
          <label className="field">KGL knowledge: the only facts it may state
            <textarea id="ai-knowledge" rows={16} disabled={!canEdit} value={form.knowledge}
              onChange={(e) => setForm({ ...form, knowledge: e.target.value })}
              placeholder="Services, routes, how to book, office hours, prices you are happy for it to quote…" />
          </label>
          {canEdit && !form.knowledge.trim() && (
            <div><button type="button" onClick={() => setForm({ ...form, knowledge: STARTER })}>Insert a starter outline</button></div>
          )}
          <label className="field">Extra instructions (optional)
            <textarea id="ai-extra" rows={3} disabled={!canEdit} value={form.extra_instructions}
              onChange={(e) => setForm({ ...form, extra_instructions: e.target.value })}
              placeholder="e.g. Always mention our Friday China air cut-off. Sign off as the KGL team." />
          </label>
          <label className="field" style={{ maxWidth: 260 }}>Most AI replies per customer per day
            <input id="ai-cap" type="number" min={1} max={100} disabled={!canEdit} value={form.max_replies_per_day}
              onChange={(e) => setForm({ ...form, max_replies_per_day: Number(e.target.value) })} />
          </label>
          {canEdit && (
            <div className="row">
              <button onClick={() => save(s.enabled)}>Save changes</button>
              {saved && <span className="ok" role="status">Saved</span>}
            </div>
          )}
          <details className="more">
            <summary>What it can and can't do</summary>
            <ul className="muted" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              <li>Can: answer from your knowledge, ask for route / goods / weight, save customer details, log quote requests, plan follow-ups, hand over to a person.</li>
              <li>Can't: set prices you haven't written, change a customer's status, record marketing consent, message anyone who said STOP, or reply after 24 hours of silence.</li>
              <li>Voice notes, images and documents go straight to your team.</li>
            </ul>
          </details>
        </section>

        <TestChat />
      </div>
    </>
  );
}

function TestChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    const message = text.trim();
    if (!message) return;
    setError("");
    setBusy(true);
    try {
      const r = await api.post<{ reply: string; actions: string[]; handoff: boolean; handoff_reason: string }>("/ai/test", {
        message, transcript: turns.map((t) => ({ role: t.role, content: t.content })),
      });
      setTurns([...turns, { role: "user", content: message }, { role: "assistant", content: r.reply || "(no reply: it would hand this to your team)", actions: r.actions, handoff: r.handoff ? r.handoff_reason : "" }]);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack summary" aria-label="Try the assistant">
      <h2>Try it as a customer</h2>
      <p className="muted" style={{ fontSize: 12.5 }}>Nothing here is saved or sent. Save your knowledge first, then test.</p>
      <div className="msgs" style={{ maxHeight: 360 }} role="log" aria-live="polite">
        {turns.map((t, i) => (
          <div key={i} className={`msg ${t.role === "user" ? "in" : "out"}`}>
            <div className="msg-body">{t.content}</div>
            {t.actions?.map((a) => <div key={a} className="msg-meta">⚙ {a}</div>)}
            {t.handoff && <div className="msg-meta"><b>Would hand over:</b> {t.handoff}</div>}
          </div>
        ))}
        {!turns.length && <p className="empty">Try: “How much to ship 2 cartons from Guangzhou?”</p>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <form className="row" style={{ alignItems: "flex-end" }} onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label className="field" style={{ flex: 1 }}>Customer message
          <input id="ai-test-input" value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <button className="primary" type="submit" disabled={busy || !text.trim()}>{busy ? "Thinking…" : "Send"}</button>
        {turns.length > 0 && <button type="button" onClick={() => setTurns([])}>Start over</button>}
      </form>
    </section>
  );
}
