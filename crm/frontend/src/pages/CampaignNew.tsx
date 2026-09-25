import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, cleanFilters } from "../api";
import FilterBuilder from "../components/FilterBuilder";
import { EXCLUDED_LABEL, ngn } from "../format";
import type { Campaign, Category, Channel, Filters, Preview, Segment } from "../types";
import { describe } from "./Segments";

type Draft = Pick<Campaign, "name" | "channel" | "category" | "segment_id" | "subject" | "body" | "media_url" | "media_type" | "wa_template_name" | "wa_template_lang"> & {
  filters: Filters;
  wa_template_params: string;
};

const EMPTY: Draft = {
  name: "", channel: "whatsapp", category: "marketing", segment_id: null, filters: {}, subject: "", body: "",
  media_url: "", media_type: "", wa_template_name: "", wa_template_lang: "en", wa_template_params: "",
};
const PLACEHOLDERS = ["first_name", "name", "city", "company", "last_route"];
const SAMPLE: Record<string, string> = { first_name: "Ada", name: "Ada Obi", city: "Ikeja", company: "Ada Stores", last_route: "china air" };
const sample = (text: string) => PLACEHOLDERS.reduce((t, k) => t.split(`{${k}}`).join(SAMPLE[k]), text);

export default function CampaignNew() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [draft, setDraft] = useState<Draft>(() => {
    let filters: Filters = {};
    try { filters = JSON.parse(params.get("f") ?? "{}"); } catch { /* ignore bad link */ }
    const seg = Number(params.get("segment")) || null;
    return { ...EMPTY, filters, segment_id: seg };
  });
  const [segments, setSegments] = useState<Segment[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [step, setStep] = useState(1);
  const [when, setWhen] = useState<"now" | "later">("now");
  const [sendAt, setSendAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [campaignId, setCampaignId] = useState<number | null>(id ? Number(id) : null);

  useEffect(() => { api.get<Segment[]>("/segments").then(setSegments).catch(() => {}); }, []);
  useEffect(() => {
    if (!id) return;
    api.get<Campaign>(`/campaigns/${id}`).then((c) => setDraft({
      name: c.name, channel: c.channel, category: c.category, segment_id: c.segment_id, filters: c.filters, subject: c.subject,
      body: c.body, media_url: c.media_url, media_type: c.media_type, wa_template_name: c.wa_template_name,
      wa_template_lang: c.wa_template_lang, wa_template_params: c.wa_template_params.join(", "),
    })).catch((e) => setError(e.message));
  }, [id]);

  const audienceKey = JSON.stringify([cleanFilters(draft.filters), draft.segment_id, draft.channel, draft.category]);
  useEffect(() => {
    const t = setTimeout(() => {
      api.post<Preview>("/campaigns/preview", { filters: cleanFilters(draft.filters), segment_id: draft.segment_id, channel: draft.channel, category: draft.category })
        .then(setPreview).catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [audienceKey]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const segment = segments.find((s) => s.id === draft.segment_id);

  function payload() {
    return {
      ...draft,
      filters: cleanFilters(draft.filters),
      wa_template_params: draft.wa_template_params.split(",").map((s) => s.trim()).filter(Boolean),
    };
  }

  async function save(): Promise<number | null> {
    setError("");
    try {
      const c = campaignId
        ? await api.put<Campaign>(`/campaigns/${campaignId}`, payload())
        : await api.post<Campaign>("/campaigns", payload());
      setCampaignId(c.id);
      return c.id;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  async function send() {
    if (when === "later" && !sendAt) { setError("Pick a date and time to send."); return; }
    setBusy(true);
    const cid = await save();
    if (cid) {
      try {
        await api.post(`/campaigns/${cid}/send`, { send_at: when === "later" ? new Date(sendAt).toISOString().slice(0, 19) : null });
        nav(`/campaigns/${cid}`);
      } catch (e) {
        setError((e as Error).message);
      }
    }
    setBusy(false);
  }

  const templateMode = draft.channel === "whatsapp" && !!draft.wa_template_name;
  const needsTemplate = draft.channel === "whatsapp" && draft.category === "marketing";

  return (
    <>
      <div className="topline">
        <h1>{id ? "Edit campaign" : "New campaign"}</h1>
        <div className="row">
          <button onClick={async () => { if (await save()) nav("/campaigns"); }} disabled={!draft.name}>Save draft</button>
        </div>
      </div>

      <div className="builder">
        <div>
          <div className="steps" role="tablist">
            {["Audience", "Message", "Send"].map((label, i) => (
              <button key={label} role="tab" aria-selected={step === i + 1} className={step === i + 1 ? "on" : ""} onClick={() => setStep(i + 1)}>
                {i + 1}. {label}
              </button>
            ))}
          </div>

          {step === 1 && (
            <div className="card stack">
              <label className="field">Campaign name<input id="c-name" required placeholder="e.g. Friday China air cut-off" value={draft.name} onChange={(e) => set("name", e.target.value)} /></label>
              <div className="grid2">
                <label className="field">Channel
                  <select id="c-channel" value={draft.channel} onChange={(e) => set("channel", e.target.value as Channel)}>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="email">Email</option>
                  </select>
                </label>
                {draft.channel === "whatsapp" && (
                  <label className="field">Message type
                    <select id="c-category" value={draft.category} onChange={(e) => set("category", e.target.value as Category)}>
                      <option value="marketing">Marketing: offers, promotions, win-back (≈₦84 each)</option>
                      <option value="utility">Update: cut-offs, shipment news for existing customers (≈₦14 each)</option>
                    </select>
                  </label>
                )}
              </div>
              <label className="field">Start from a saved segment
                <select id="c-segment" value={draft.segment_id ?? ""} onChange={(e) => set("segment_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">No segment: use the filters below</option>
                  {segments.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.count})</option>)}
                </select>
              </label>
              {segment && <p className="muted">Segment: {describe(segment.filters)}. Filters below narrow it further.</p>}
              <FilterBuilder value={draft.filters} onChange={(f) => set("filters", f)} />
              <div><button className="primary" onClick={() => setStep(2)} disabled={!draft.name}>Next: message</button></div>
            </div>
          )}

          {step === 2 && (
            <div className="card stack">
              {draft.channel === "email" && (
                <label className="field">Subject<input id="c-subject" value={draft.subject} onChange={(e) => set("subject", e.target.value)} /></label>
              )}
              {draft.channel === "whatsapp" && (
                <div className="stack" style={{ background: "#fafbf9", border: "1px solid var(--rule-2)", borderRadius: 8, padding: 12 }}>
                  <p style={{ fontSize: 13 }}>
                    <b>WhatsApp template{needsTemplate ? " (required for marketing)" : " (optional)"}.</b>{" "}
                    <span className="muted">Meta only lets businesses message customers who haven't written in the last 24 hours using pre-approved templates. Use the template name exactly as approved in Meta Business Manager.</span>
                  </p>
                  <div className="grid2">
                    <label className="field">Template name<input id="c-template" placeholder="e.g. cutoff_reminder" value={draft.wa_template_name} onChange={(e) => set("wa_template_name", e.target.value)} /></label>
                    <label className="field">Language code<input id="c-lang" value={draft.wa_template_lang} onChange={(e) => set("wa_template_lang", e.target.value)} /></label>
                  </div>
                  {templateMode && (
                    <label className="field">Fill template variables {"{{1}}, {{2}}…"} with (comma separated)
                      <input id="c-params" placeholder="first_name, city" value={draft.wa_template_params} onChange={(e) => set("wa_template_params", e.target.value)} />
                    </label>
                  )}
                </div>
              )}
              <label className="field">
                {templateMode ? "Message text for the preview and timeline (the approved template is what's sent)" : "Message"}
                <textarea id="c-body" rows={7} value={draft.body} onChange={(e) => set("body", e.target.value)} placeholder="Hi {first_name}, the China air consolidation closes Friday 5pm…" />
              </label>
              <p className="muted" style={{ fontSize: 12.5 }}>
                Personalise with {PLACEHOLDERS.map((p) => (
                  <button key={p} type="button" className="ghost mono" style={{ padding: "0 4px" }} onClick={() => set("body", `${draft.body}{${p}}`)}>{`{${p}}`}</button>
                ))}
              </p>
              <div className="grid2">
                <label className="field">Attachment link (optional)<input id="c-media" placeholder="https://… flyer.jpg / rates.pdf" value={draft.media_url} onChange={(e) => set("media_url", e.target.value)} /></label>
                <label className="field">Attachment type
                  <select id="c-media-type" value={draft.media_type} onChange={(e) => set("media_type", e.target.value as Draft["media_type"])}>
                    <option value="">None</option><option value="image">Image / flyer</option><option value="video">Video</option><option value="document">PDF / document</option>
                  </select>
                </label>
              </div>
              <div className="row"><button onClick={() => setStep(1)}>Back</button><button className="primary" onClick={() => setStep(3)}>Next: send</button></div>
            </div>
          )}

          {step === 3 && (
            <div className="card stack">
              <label className="check"><input type="radio" name="when" checked={when === "now"} onChange={() => setWhen("now")} /> Send now</label>
              <label className="check"><input type="radio" name="when" checked={when === "later"} onChange={() => setWhen("later")} /> Schedule for later</label>
              {when === "later" && (
                <label className="field" style={{ maxWidth: 280 }}>Send at (your local time)<input id="c-send-at" type="datetime-local" value={sendAt} onChange={(e) => setSendAt(e.target.value)} /></label>
              )}
              {preview && (
                <p>
                  This sends to <b>{preview.will_receive.toLocaleString()}</b> customer{preview.will_receive === 1 ? "" : "s"}
                  {draft.channel === "whatsapp" && <> at an estimated <b>{ngn(preview.estimated_cost_ngn)}</b> in Meta fees</>}.
                  {preview.test_mode && <> <b>Test mode:</b> nothing will actually be sent.</>}
                </p>
              )}
              {error && <p className="error" role="alert">{error}</p>}
              <div className="row">
                <button onClick={() => setStep(2)}>Back</button>
                <button className="primary" onClick={send} disabled={busy || !preview?.will_receive}>
                  {busy ? "Starting…" : when === "now" ? `Send to ${preview?.will_receive ?? 0}` : "Schedule campaign"}
                </button>
              </div>
            </div>
          )}
          {error && step !== 3 && <p className="error" style={{ marginTop: 10 }}>{error}</p>}
        </div>

        <aside className="card summary stack" aria-label="Audience summary">
          <div>
            <span className="muted">Will receive</span>
            <div className="big">{preview ? preview.will_receive.toLocaleString() : "—"}</div>
            {preview && <span className="muted">of {preview.matched.toLocaleString()} matching customers</span>}
          </div>
          {preview && Object.values(preview.excluded).some(Boolean) && (
            <ul className="exclusions">
              {Object.entries(preview.excluded).filter(([, n]) => n > 0).map(([k, n]) => (
                <li key={k}><span>{EXCLUDED_LABEL[k] ?? k}</span><span className="num">−{n}</span></li>
              ))}
            </ul>
          )}
          {preview && draft.channel === "whatsapp" && (
            <p>Estimated Meta fees: <b>{ngn(preview.estimated_cost_ngn)}</b><br /><span className="muted" style={{ fontSize: 12 }}>{ngn(preview.fee_per_message_ngn)} per delivered message</span></p>
          )}
          <div className="phone" aria-label="Message preview">
            <div className="bubble">
              {draft.media_type && <div className="media">{draft.media_type === "document" ? "PDF / document" : draft.media_type === "video" ? "Video" : "Image"}</div>}
              {draft.channel === "email" && draft.subject && <b>{sample(draft.subject)}{"\n"}</b>}
              {sample(draft.body) || <span className="muted">Your message will appear here.</span>}
            </div>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>Preview uses a sample customer (Ada Obi, Ikeja).</p>
        </aside>
      </div>
    </>
  );
}
