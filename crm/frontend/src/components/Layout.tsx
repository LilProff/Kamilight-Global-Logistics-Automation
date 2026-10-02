import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken } from "../api";
import type { Me, Stats } from "../types";
import Logo from "./Logo";

export default function Layout() {
  const nav = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [waLive, setWaLive] = useState<boolean | null>(null);

  useEffect(() => {
    api.get<Me>("/auth/me").then(setMe).catch(() => {});
    api.get<Stats>("/stats").then((s) => setWaLive(s.channels.whatsapp)).catch(() => {});
  }, []);

  function signOut() {
    setToken(null);
    nav("/login");
  }

  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">
          <Logo variant="white" height={26} />
          <span className="brand-sub">Customers</span>
        </div>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/customers">Customers</NavLink>
        <NavLink to="/segments">Segments</NavLink>
        <NavLink to="/campaigns">Campaigns</NavLink>
        <NavLink to="/automations">Automations</NavLink>
        <NavLink to="/team">{me?.role === "admin" ? "Team" : "My account"}</NavLink>
        <div className="spacer" />
        <div className="who">
          {me?.name || me?.email}
          {me && me.name.toLowerCase() !== (me.role === "admin" ? "administrator" : "staff") && (
            <span className="role">{me.role === "admin" ? "Administrator" : "Staff"}</span>
          )}
        </div>
        <button className="ghost" style={{ color: "#c9d2d9" }} onClick={signOut}>
          Sign out
        </button>
      </nav>
      <main className="main">
        {waLive === false && (
          <div className="banner" role="status">
            <b>Test mode.</b> WhatsApp isn't connected yet, so campaigns run end to end but no messages actually leave. Add
            KGL's WhatsApp Business credentials to go live.
          </div>
        )}
        {me ? <Outlet context={{ me }} /> : <p className="muted">Loading…</p>}
      </main>
    </div>
  );
}
