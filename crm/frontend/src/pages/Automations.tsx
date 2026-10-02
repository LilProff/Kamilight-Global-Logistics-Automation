import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api";
import { Dialog } from "../components/ui";
import { dateTime, ngn } from "../format";
import type { AutomationView, Me } from "../types";

const PLACEHOLDERS = ["first_name", "name", "city", "company", "last_route"];
const SAMPLE: Record<string, string> = { first_name: "Ada", name: "Ada Obi", city: "Ikeja", company: "Ada Stores", last_route: "china air" };
const sample = (t: string) => PLACEHOLDERS.reduce((s, k) => s.split(`{${k}}`).join(SAMPLE[k]), t);

export default function Automations() {
  const { me } = useOutletContext<{ me: Me }>();
  const [items, setItems] = useState<AutomationView[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<AutomationView[]>("/automations").then(setItems).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <>
      <div className="topline">
        <h1>Automations</h1>
      </div>
      <p className="muted" style={{ marginBottom: 16, maxWidth: "70ch" }}>
        Messages that send themselves. Each one is <b>off until you switch it on</b>, only runs during the day (08:00–19:00 Lagos
        time), never messages the same person twice within its cool-down, and respects who has agreed to receive messages.
        Everything they send appears under Campaigns, so you can see exactly what went out.
      </p>
      {me.role !== "admin" && <p className="banner">Only an administrator can change automations. You can see how they're doing.</p>}
      {error && <p className="error">{error}</p>}
      <div className="stack" style={{ gap: 16 }}>
        {items?.map((a) => <AutomationCard key={a.key} item={a} canEdit={me.role === "admin"} onSaved={load} />)}
      </div>
    </>
  );
}

function AutomationCard({ item, canEdit, onSaved }: { item: AutomationView; canEdit: boolean; onSaved: () => void }) {
  const [form, setForm] = useState({
    body: item.body, days: item.days, cooldown_days: item.cooldown_days, daily_limit: item.daily_limit,
    wa_template_name: item.wa_template_name, wa_template_params: item.wa_template_params.join(", "),
  });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const payload = (enabled: boolean) => ({
    enabled, body: form.body, days: Number(form.days), cooldown_days: Number(form.cooldown_days), daily_limit: Number(form.daily_limit),
    wa_template_name: form.wa_template_name.trim(), wa_template_lang: item.wa_template_lang,
    wa_template_params: form.wa_template_params.split(",").map((s) => s.trim()).filter(Boolean),
  });

  async function save(enabled: boolean) {
    setError("");
    try {
      await api.put(`/automations/${item.key}`, payload(enabled));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      setConfirm(false);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
      setConfirm(false);
    }
  }

  const p = item.preview;
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <section className="card automation" aria-label={item.title}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{item.title}</h2>
          <p className="muted" style={{ maxWidth: "65ch" }}>{item.summary}</p>
        </div>
        <div className="row">
          <span className={`pill ${item.enabled ? "cs-sent" : "cs-draft"}`}>{item.enabled ? "On" : "Off"}</span>
          {canEdit && (
            item.enabled
              ? <button onClick={() => save(false)}>Switch off</button>
              : <button className="primary" onClick={() => (p.blocked_reason ? setError(p.blocked_reason) : setConfirm(true))}>Switch on</button>
          )}
        </div>
      </div>

      <div className="facts" style={{ marginTop: 14 }}>
        <div><span className="muted">Qualify right now</span><b className="num">{p.qualifies_now}</b></div>
        <div><span className="muted">Next batch</span><b className="num">{p.next_batch}</b></div>
        <div><span className="muted">Sent today</span><b className="num">{p.sent_today} / {p.daily_limit}</b></div>
        <div><span className="muted">Sent so far</span><b className="num">{item.sent_total}</b></div>
        <div><span className="muted">Last sent</span><b>{item.last_sent_at ? dateTime(item.last_sent_at) : "never"}</b></div>
      </div>
      {item.enabled && !item.in_sending_hours && <p className="muted" style={{ marginTop: 8 }}>It's outside sending hours, so nothing goes out until 08:00 Lagos time.</p>}
      {p.test_mode && <p className="muted" style={{ marginTop: 8 }}>Test mode: messages are queued and counted but nothing actually leaves until WhatsApp is connected.</p>}

      <div className="builder" style={{ marginTop: 16, gridTemplateColumns: "minmax(0, 1fr) 280px" }}>
        <div className="stack">
          <label className="field">Message
            <textarea id={`auto-${item.key}-body`} rows={5} disabled={!canEdit} value={form.body} onChange={(e) => set("body", e.target.value)} />
          </label>
          <p className="muted" style={{ fontSize: 12.5 }}>
            Personalise with {PLACEHOLDERS.map((x) => (
              <button key={x} type="button" className="ghost mono" disabled={!canEdit} style={{ padding: "0 4px" }} onClick={() => set("body", `${form.body}{${x}}`)}>{`{${x}}`}</button>
            ))}
          </p>
          <div className="grid2">
            {item.uses_days && (
              <label className="field">Follow up after (days)
                <input id={`auto-${item.key}-days`} type="number" min={0} max={60} disabled={!canEdit} value={form.days} onChange={(e) => set("days", Number(e.target.value))} />
              </label>
            )}
            <label className="field">Don't message the same person again for (days)
              <input id={`auto-${item.key}-cooldown`} type="number" min={1} disabled={!canEdit} value={form.cooldown_days} onChange={(e) => set("cooldown_days", Number(e.target.value))} />
            </label>
            <label className="field">Most messages per day
              <input id={`auto-${item.key}-limit`} type="number" min={1} max={500} disabled={!canEdit} value={form.daily_limit} onChange={(e) => set("daily_limit", Number(e.target.value))} />
            </label>
          </div>
          <details className="more">
            <summary>WhatsApp template {item.category === "marketing" ? "(required once WhatsApp is live)" : "(optional)"}</summary>
            <div className="grid2" style={{ marginTop: 10 }}>
              <label className="field">Approved template name
                <input id={`auto-${item.key}-template`} placeholder="e.g. winback_offer" disabled={!canEdit} value={form.wa_template_name} onChange={(e) => set("wa_template_name", e.target.value)} />
              </label>
              <label className="field">Template variables (comma separated)
                <input id={`auto-${item.key}-params`} placeholder="first_name" disabled={!canEdit} value={form.wa_template_params} onChange={(e) => set("wa_template_params", e.target.value)} />
              </label>
            </div>
          </details>
          {error && <p className="error" role="alert">{error}</p>}
          {canEdit && (
            <div className="row">
              <button onClick={() => save(item.enabled)}>Save changes</button>
              {saved && <span className="ok" role="status">Saved</span>}
            </div>
          )}
        </div>
        <div className="phone" aria-label="Message preview">
          <div className="bubble">{sample(form.body) || <span className="muted">Your message will appear here.</span>}</div>
        </div>
      </div>

      {confirm && (
        <Dialog title={`Switch on "${item.title}"?`} onClose={() => setConfirm(false)}>
          <p>
            About <b>{p.qualifies_now}</b> customer{p.qualifies_now === 1 ? "" : "s"} qualify right now. Up to <b>{form.daily_limit}</b> a day will be
            messaged, starting with the next daytime check.
          </p>
          {item.category === "marketing"
            ? <p>Only customers who agreed to receive offers are included. Each message costs about <b>{ngn(p.fee_per_message_ngn)}</b> (up to {ngn(p.estimated_cost_ngn)} on the first day).</p>
            : <p>These are service messages to customers who contacted KGL. Each costs about <b>{ngn(p.fee_per_message_ngn)}</b>.</p>}
          {p.test_mode && <p className="muted">WhatsApp isn't connected, so this is a rehearsal: nothing will actually be sent.</p>}
          <div className="row">
            <button className="primary" onClick={() => save(true)}>Yes, switch on</button>
            <button onClick={() => setConfirm(false)}>Not yet</button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
