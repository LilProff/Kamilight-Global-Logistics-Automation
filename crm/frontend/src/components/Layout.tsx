import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken } from "../api";
import type { Stats } from "../types";

export default function Layout() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [waLive, setWaLive] = useState<boolean | null>(null);

  useEffect(() => {
    api.get<{ email: string }>("/auth/me").then((r) => setEmail(r.email)).catch(() => {});
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
          KGL <span>·</span> Customers
        </div>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/customers">Customers</NavLink>
        <NavLink to="/segments">Segments</NavLink>
        <NavLink to="/campaigns">Campaigns</NavLink>
        <div className="spacer" />
        <div className="who">{email}</div>
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
        <Outlet />
      </main>
    </div>
  );
}
