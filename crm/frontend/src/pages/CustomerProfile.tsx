import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { refreshOptions, useOptions } from "../components/FilterBuilder";
import { Dialog, StatusPill } from "../components/ui";
import { date, dateTime, daysAgo, ngn, routeLabel, SOURCE_LABEL, STATUS_LABEL, TYPE_LABEL } from "../format";
import type { ContactDetail, CustomerType, Status } from "../types";

type Draft = Pick<ContactDetail, "name" | "phone" | "email" | "company" | "city" | "customer_type" | "goods" | "preferred_mode" | "assigned_to" | "notes" | "birthday"> & {
  routes: string;
  tags: string;
};

const toDraft = (c: ContactDetail): Draft => ({
  name: c.name, phone: c.phone ?? "", email: c.email ?? "", company: c.company, city: c.city, customer_type: c.customer_type,
  goods: c.goods, preferred_mode: c.preferred_mode, assigned_to: c.assigned_to, notes: c.notes, birthday: c.birthday,
  routes: c.routes.join(", "), tags: c.tags.join(", "),
});
const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function CustomerProfile() {
  const { id } = useParams();
  const nav = useNavigate();
  const options = useOptions();
  const [c, setC] = useState<ContactDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [dialog, setDialog] = useState<"" | "shipment" | "quote" | "delete">("");
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api.get<ContactDetail>(`/contacts/${id}`).then((d) => { setC(d); setDraft(toDraft(d)); }).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  async function patch(body: object, message = "Saved") {
    setError("");
    try {
      await api.patch(`/contacts/${id}`, body);
      setSaved(message);
      setTimeout(() => setSaved(""), 2500);
      refreshOptions();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveDetails(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    await patch({ ...draft, phone: draft.phone || null, email: draft.email || null, routes: splitList(draft.routes), tags: splitList(draft.tags) }, "Details saved");
  }

  async function addNote(e: FormEvent) {
    e.preventDefault();
    await api.post(`/contacts/${id}/notes`, { text: note });
    setNote("");
    load();
  }

  if (error && !c) return <p className="error">{error}</p>;
  if (!c || !draft) return <p className="muted">Loading…</p>;
  const set = (k: keyof Draft, v: string) => setDraft({ ...draft, [k]: v });

  return (
    <>
      <div className="topline">
        <div>
          <p className="muted"><Link to="/customers">Customers</Link> /</p>
          <h1>{c.name || c.phone || c.email}</h1>
          <div className="row" style={{ marginTop: 6 }}>
            <StatusPill status={c.status} />
            <span className="muted">{TYPE_LABEL[c.customer_type]} · from {SOURCE_LABEL[c.source] ?? c.source} · added {date(c.created_at)}</span>
          </div>
        </div>
        <div className="row">
          <button onClick={() => setDialog("quote")}>Log a quote</button>
          <button className="primary" onClick={() => setDialog("shipment")}>Record shipment</button>
        </div>
      </div>

      <div className="facts card" style={{ marginBottom: 16 }}>
        <div><span className="muted">Shipments</span><b className="num">{c.shipments_count}</b></div>
        <div><span className="muted">Total spend</span><b className="num">{ngn(c.total_spend_ngn)}</b></div>
        <div><span className="muted">Last shipment</span><b>{daysAgo(c.last_shipment_at)}</b></div>
        <div><span className="muted">Last route</span><b>{c.last_route ? routeLabel(c.last_route) : "—"}</b></div>
        <div><span className="muted">Last message from them</span><b>{daysAgo(c.last_inbound_at)}</b></div>
      </div>

      <div className="profile">
        <div className="stack">
          <form className="card stack" onSubmit={saveDetails}>
            <h2>Details</h2>
            <div className="grid2">
              <label className="field">Name<input id="p-name" value={draft.name} onChange={(e) => set("name", e.target.value)} /></label>
              <label className="field">WhatsApp number<input id="p-phone" value={draft.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></label>
              <label className="field">Email<input id="p-email" type="email" value={draft.email ?? ""} onChange={(e) => set("email", e.target.value)} /></label>
              <label className="field">Company<input id="p-company" value={draft.company} onChange={(e) => set("company", e.target.value)} /></label>
              <label className="field">City / area<input id="p-city" value={draft.city} onChange={(e) => set("city", e.target.value)} /></label>
              <label className="field">Customer type
                <select id="p-type" value={draft.customer_type} onChange={(e) => set("customer_type", e.target.value as CustomerType)}>
                  {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="field">Routes (comma separated)
                <input id="p-routes" list="route-options" value={draft.routes} onChange={(e) => set("routes", e.target.value)} placeholder="china-air, lagos-uk" />
              </label>
              <label className="field">Air or sea
                <select id="p-mode" value={draft.preferred_mode} onChange={(e) => set("preferred_mode", e.target.value)}>
                  <option value="">Not known</option><option value="air">Air</option><option value="sea">Sea</option><option value="both">Both</option>
                </select>
              </label>
              <label className="field">Goods they ship<input id="p-goods" value={draft.goods} onChange={(e) => set("goods", e.target.value)} placeholder="e.g. phone accessories, foodstuff" /></label>
              <label className="field">Tags (comma separated)<input id="p-tags" value={draft.tags} onChange={(e) => set("tags", e.target.value)} /></label>
              <label className="field">Assigned to<input id="p-assigned" value={draft.assigned_to} onChange={(e) => set("assigned_to", e.target.value)} /></label>
              <label className="field">Birthday (MM-DD)<input id="p-birthday" value={draft.birthday} onChange={(e) => set("birthday", e.target.value)} placeholder="12-25" /></label>
            </div>
            <datalist id="route-options">{options?.routes.map((r) => <option key={r} value={r} />)}</datalist>
            <label className="field">Private notes<textarea id="p-notes" value={draft.notes} onChange={(e) => set("notes", e.target.value)} /></label>
            <div className="row">
              <button className="primary">Save details</button>
              {saved && <span className="ok" role="status">{saved}</span>}
              {error && <span className="error">{error}</span>}
            </div>
          </form>

          <div className="card stack">
            <h2>Status and consent</h2>
            <div className="grid2">
              <label className="field">Status
                <select id="p-status" value={c.status} onChange={(e) => {
                  const next = e.target.value as Status;
                  const reason = next === "lost" ? window.prompt("Why was this customer lost?") ?? "" : undefined;
                  patch({ status: next, ...(reason !== undefined ? { lost_reason: reason } : {}) }, "Status updated");
                }}>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              {c.status === "lost" && c.lost_reason && <p className="muted">Lost because: {c.lost_reason}</p>}
            </div>
            <p className="muted" style={{ fontSize: 13 }}>Statuses also update themselves: a logged quote sets Quoted, shipments set Booked, Repeat or VIP, and 60 days without shipping sets Dormant.</p>
            {c.wa_opted_out ? (
              <p className="error">This customer replied STOP. They won't receive WhatsApp campaigns.</p>
            ) : (
              <label className="check">
                <input type="checkbox" checked={c.wa_opt_in} onChange={(e) => patch({ wa_opt_in: e.target.checked }, "Consent updated")} />
                <span>Agreed to receive WhatsApp offers and updates{c.wa_opt_in_at ? ` (since ${date(c.wa_opt_in_at)})` : ""}</span>
              </label>
            )}
            <label className="check">
              <input type="checkbox" checked={c.do_not_contact} onChange={(e) => patch({ do_not_contact: e.target.checked }, "Updated")} />
              <span>Do not contact: excluded from every campaign</span>
            </label>
            <div><button className="danger ghost" onClick={() => setDialog("delete")}>Delete customer</button></div>
          </div>
        </div>

        <div className="card">
          <h2>Timeline</h2>
          <form className="row" onSubmit={addNote} style={{ marginBottom: 12 }}>
            <input id="note" style={{ flex: 1, width: "auto" }} placeholder="Add a note (call summary, promise, reminder)" value={note} onChange={(e) => setNote(e.target.value)} />
            <button disabled={!note.trim()}>Add</button>
          </form>
          <ul className="timeline">
            {c.events.map((e) => (
              <li key={e.id} className={`k-${e.kind}`}>
                <div><b>{e.title}</b>{e.amount_ngn != null && <span className="num"> · {ngn(e.amount_ngn)}</span>}</div>
                <div className="when">{dateTime(e.created_at)}</div>
                {e.detail && <div className="detail">{e.detail}</div>}
              </li>
            ))}
          </ul>
          {c.events.length === 0 && <p className="muted">Nothing yet.</p>}
        </div>
      </div>

      {dialog === "shipment" && <ShipmentDialog id={c.id} onClose={() => setDialog("")} onDone={() => { setDialog(""); load(); }} />}
      {dialog === "quote" && <QuoteDialog id={c.id} onClose={() => setDialog("")} onDone={() => { setDialog(""); load(); }} />}
      {dialog === "delete" && (
        <Dialog title="Delete this customer?" onClose={() => setDialog("")}>
          <p>This permanently removes {c.name || "this customer"} and their timeline. Campaign reports keep their counts.</p>
          <div className="row">
            <button className="primary" style={{ background: "var(--bad)", borderColor: "var(--bad)" }} onClick={async () => { await api.del(`/contacts/${c.id}`); nav("/customers"); }}>Delete</button>
            <button onClick={() => setDialog("")}>Keep customer</button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function ShipmentDialog({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: () => void }) {
  const options = useOptions();
  const [amount, setAmount] = useState("");
  const [route, setRoute] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post(`/contacts/${id}/shipments`, { amount_ngn: Number(amount), route, note });
      refreshOptions();
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Dialog title="Record a shipment" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <div className="grid2">
          <label className="field">Amount charged (₦)<input id="ship-amount" type="number" min={0} required value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
          <label className="field">Route
            <select id="ship-route" value={route} onChange={(e) => setRoute(e.target.value)}>
              <option value="">Not specified</option>
              {options?.routes.map((r) => <option key={r} value={r}>{routeLabel(r)}</option>)}
            </select>
          </label>
        </div>
        <label className="field">Note (optional)<input id="ship-note" placeholder="e.g. 42 kg, 3 cartons" value={note} onChange={(e) => setNote(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="row"><button className="primary">Record shipment</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}

function QuoteDialog({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    await api.post(`/contacts/${id}/quote`, { text });
    onDone();
  }
  return (
    <Dialog title="Log a quote" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">What was quoted<textarea id="quote-text" required placeholder="e.g. China air, 30 kg at $7.20/kg, door delivery Ikeja" value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="row"><button className="primary">Save quote</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}
