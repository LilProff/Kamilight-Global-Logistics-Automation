import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";
import { api, setToken } from "../api";
import { Dialog } from "../components/ui";
import { dateTime } from "../format";
import type { Me, TeamUser } from "../types";

/** A strong, readable password the administrator can hand to a colleague (they can change it after signing in). */
function suggestPassword(): string {
  const words = ["river", "lantern", "harbour", "cedar", "market", "falcon", "amber", "coast", "maple", "sunrise", "granite", "violet"];
  const pick = (n: number) => crypto.getRandomValues(new Uint32Array(1))[0] % n;
  return `${words[pick(words.length)]}-${words[pick(words.length)]}-${10 + pick(90)}-${words[pick(words.length)]}`;
}

export default function Team() {
  const { me } = useOutletContext<{ me: Me }>();
  return (
    <>
      <div className="topline"><h1>{me.role === "admin" ? "Team" : "My account"}</h1></div>
      <div className="stack" style={{ gap: 16 }}>
        <ChangePassword me={me} />
        {me.role === "admin" && <Members me={me} />}
      </div>
    </>
  );
}

function ChangePassword({ me }: { me: Me }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next !== again) { setMsg({ ok: false, text: "The two new passwords don't match." }); return; }
    try {
      const r = await api.post<{ token: string }>("/auth/change-password", { current_password: current, new_password: next });
      setToken(r.token); // this device stays signed in; every other device is signed out
      setCurrent(""); setNext(""); setAgain("");
      setMsg({ ok: true, text: "Password changed. Any other device you were signed in on has been signed out." });
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    }
  }

  return (
    <form className="card stack" onSubmit={submit} style={{ maxWidth: 520 }}>
      <h2>Change my password</h2>
      <p className="muted">Signed in as <b>{me.name || me.email}</b> ({me.email}). Use at least 10 characters and avoid your name or common words.</p>
      <label className="field">Current password<input id="pw-current" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
      <label className="field">New password<input id="pw-new" type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} /></label>
      <label className="field">New password again<input id="pw-again" type="password" autoComplete="new-password" required value={again} onChange={(e) => setAgain(e.target.value)} /></label>
      {msg && <p className={msg.ok ? "ok" : "error"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}
      <div><button className="primary">Change password</button></div>
    </form>
  );
}

function Members({ me }: { me: Me }) {
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<null | "add" | TeamUser>(null);
  const load = useCallback(() => { api.get<TeamUser[]>("/users").then(setUsers).catch((e) => setError(e.message)); }, []);
  useEffect(load, [load]);

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Staff accounts</h2>
        <button className="primary" onClick={() => setDialog("add")}>Add staff member</button>
      </div>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Everyone signs in with their own email and password. <b>Administrators</b> manage staff and automations; <b>staff</b> work with
        customers, segments and campaigns. Deactivating someone signs them out straight away.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name || "—"}</b>{u.id === me.id && <span className="chip" style={{ marginLeft: 6 }}>you</span>}</td>
                <td className="mono">{u.email}</td>
                <td>{u.role === "admin" ? "Administrator" : "Staff"}</td>
                <td><span className={`pill ${u.active ? "st-booked" : "st-dormant"}`}>{u.active ? "Active" : "Deactivated"}</span></td>
                <td>{u.last_login_at ? dateTime(u.last_login_at) : "never"}</td>
                <td className="right"><button onClick={() => setDialog(u)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dialog === "add" && <AddMember onClose={() => setDialog(null)} onDone={() => { setDialog(null); load(); }} />}
      {dialog && dialog !== "add" && <EditMember user={dialog} me={me} onClose={() => setDialog(null)} onDone={() => { setDialog(null); load(); }} />}
    </div>
  );
}

function AddMember({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: "", email: "", role: "staff", password: "" });
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await api.post("/users", f); onDone(); } catch (err) { setError((err as Error).message); }
  }
  return (
    <Dialog title="Add staff member" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">Name<input id="new-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label className="field">Email<input id="new-email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="field">Role
          <select id="new-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option value="staff">Staff</option><option value="admin">Administrator</option>
          </select>
        </label>
        <label className="field">Starting password
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="new-password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            <button type="button" onClick={() => setF({ ...f, password: suggestPassword() })}>Suggest</button>
          </div>
        </label>
        <p className="muted" style={{ fontSize: 12.5 }}>Tell them this password in person or by phone, and ask them to change it after signing in.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row"><button className="primary">Add staff member</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}

function EditMember({ user, me, onClose, onDone }: { user: TeamUser; me: Me; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: user.name, role: user.role, active: user.active, password: "" });
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = { name: f.name, role: f.role, active: f.active };
    if (f.password) body.password = f.password;
    try { await api.patch(`/users/${user.id}`, body); onDone(); } catch (err) { setError((err as Error).message); }
  }
  const self = user.id === me.id;
  return (
    <Dialog title={`Edit ${user.name || user.email}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">Name<input id="edit-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label className="field">Role
          <select id="edit-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as "admin" | "staff" })}>
            <option value="staff">Staff</option><option value="admin">Administrator</option>
          </select>
        </label>
        <label className="check">
          <input id="edit-active" type="checkbox" checked={f.active} disabled={self} onChange={(e) => setF({ ...f, active: e.target.checked })} />
          <span>Account is active{self ? " (you can't deactivate yourself)" : ""}</span>
        </label>
        <label className="field">Reset password (leave blank to keep it)
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="edit-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            <button type="button" onClick={() => setF({ ...f, password: suggestPassword() })}>Suggest</button>
          </div>
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row"><button className="primary">Save</button><button type="button" onClick={onClose}>Cancel</button></div>
      </form>
    </Dialog>
  );
}
