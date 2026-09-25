import { useEffect, useState } from "react";
import { api } from "../api";
import { routeLabel, SOURCE_LABEL, STATUS_LABEL, TYPE_LABEL } from "../format";
import type { Filters, Options } from "../types";

let cachedOptions: Promise<Options> | null = null;
export function useOptions() {
  const [options, setOptions] = useState<Options | null>(null);
  useEffect(() => {
    cachedOptions ??= api.get<Options>("/contacts/options");
    cachedOptions.then(setOptions).catch(() => (cachedOptions = null));
  }, []);
  return options;
}
export function refreshOptions() {
  cachedOptions = null;
}

function Multi<T extends string>({
  label, values, selected, onChange, labelFor,
}: {
  label: string;
  values: T[];
  selected: T[] | undefined;
  onChange: (next: T[]) => void;
  labelFor?: (v: T) => string;
}) {
  const sel = selected ?? [];
  if (!values.length) return null;
  return (
    <div className="field" style={{ display: "grid", gap: 4 }}>
      <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-2)" }}>{label}</span>
      <div className="multi">
        {values.map((v) => {
          const on = sel.includes(v);
          return (
            <button
              key={v}
              type="button"
              className={on ? "on" : ""}
              aria-pressed={on}
              onClick={() => onChange(on ? sel.filter((x) => x !== v) : [...sel, v])}
            >
              {labelFor ? labelFor(v) : v}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function NumberField({ label, value, onChange, placeholder }: {
  label: string; value: number | "" | undefined; onChange: (v: number | "") => void; placeholder?: string;
}) {
  return (
    <label className="field">
      {label}
      <input
        type="number"
        min={0}
        inputMode="numeric"
        placeholder={placeholder}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    </label>
  );
}

export default function FilterBuilder({ value, onChange }: { value: Filters; onChange: (f: Filters) => void }) {
  const options = useOptions();
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) => onChange({ ...value, [key]: v });
  if (!options) return <p className="muted">Loading filters…</p>;

  return (
    <div className="filters">
      <Multi label="Status" values={options.statuses} selected={value.statuses} onChange={(v) => set("statuses", v)} labelFor={(s) => STATUS_LABEL[s]} />
      <Multi label="Route" values={options.routes} selected={value.routes_any} onChange={(v) => set("routes_any", v)} labelFor={routeLabel} />
      <Multi label="Customer type" values={options.customer_types} selected={value.customer_types} onChange={(v) => set("customer_types", v)} labelFor={(t) => TYPE_LABEL[t]} />
      <div className="grid">
        <NumberField label="Not shipped for (days)" placeholder="e.g. 60" value={value.not_shipped_for_days} onChange={(v) => set("not_shipped_for_days", v)} />
        <NumberField label="Shipped in the last (days)" placeholder="e.g. 90" value={value.shipped_within_days} onChange={(v) => set("shipped_within_days", v)} />
        <NumberField label="At least this many shipments" value={value.min_shipments} onChange={(v) => set("min_shipments", v)} />
        <NumberField label="Total spend at least (₦)" value={value.min_spend} onChange={(v) => set("min_spend", v)} />
      </div>
      <details className="more">
        <summary>More filters</summary>
        <div className="filters" style={{ marginTop: 10 }}>
          <Multi label="Source" values={options.sources} selected={value.sources} onChange={(v) => set("sources", v)} labelFor={(s) => SOURCE_LABEL[s] ?? s} />
          <Multi label="Tags" values={options.tags} selected={value.tags_any} onChange={(v) => set("tags_any", v)} />
          <Multi label="City" values={options.cities} selected={value.cities} onChange={(v) => set("cities", v)} />
          <div className="grid">
            <NumberField label="At most this many shipments" value={value.max_shipments} onChange={(v) => set("max_shipments", v)} />
            <NumberField label="Total spend at most (₦)" value={value.max_spend} onChange={(v) => set("max_spend", v)} />
            {options.staff.length > 0 && (
              <label className="field">
                Assigned to
                <select value={value.assigned_to ?? ""} onChange={(e) => set("assigned_to", e.target.value)}>
                  <option value="">Anyone</option>
                  {options.staff.map((s) => <option key={s}>{s}</option>)}
                </select>
              </label>
            )}
          </div>
          <label className="check">
            <input type="checkbox" checked={!!value.never_shipped} onChange={(e) => set("never_shipped", e.target.checked)} />
            Never shipped (enquiries only)
          </label>
          <label className="check">
            <input type="checkbox" checked={!!value.opted_in_only} onChange={(e) => set("opted_in_only", e.target.checked)} />
            Agreed to WhatsApp marketing only
          </label>
        </div>
      </details>
    </div>
  );
}
