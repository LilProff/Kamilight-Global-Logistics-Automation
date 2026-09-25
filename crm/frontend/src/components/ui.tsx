import { useEffect, type ReactNode } from "react";
import { STATUS_LABEL } from "../format";
import type { Status } from "../types";

export function StatusPill({ status }: { status: Status }) {
  return <span className={`pill st-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>{title}</h2>
          <button className="ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Tile({ label, value, accent }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className={`tile${accent ? " accent" : ""}`}>
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}
