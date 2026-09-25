import type { CustomerType, Status } from "./types";

export const STATUS_LABEL: Record<Status, string> = {
  new: "New enquiry",
  quoted: "Quoted",
  booked: "Booked",
  repeat: "Repeat",
  vip: "VIP",
  dormant: "Dormant",
  lost: "Lost",
};

export const TYPE_LABEL: Record<CustomerType, string> = {
  individual: "Individual",
  online_seller: "Online seller",
  business: "Business",
  diaspora: "Diaspora sender",
  partner: "Partner / agent",
};

export const SOURCE_LABEL: Record<string, string> = {
  old_list: "Old customer list",
  whatsapp: "WhatsApp",
  ad: "Ad",
  referral: "Referral",
  partner: "Partner",
  walk_in: "Walk-in",
  website: "Website",
  apollo: "Apollo",
  manual: "Added by staff",
};

export const EXCLUDED_LABEL: Record<string, string> = {
  do_not_contact: "Marked do not contact",
  no_phone: "No WhatsApp number",
  opted_out: "Replied STOP",
  no_marketing_consent: "No marketing consent",
  no_email: "No email address",
};

const ROUTE_LABEL: Record<string, string> = {
  "china-air": "China → Lagos (air)",
  "china-sea": "China → Lagos (sea)",
  "uk-import": "UK → Lagos",
  "us-import": "US → Lagos",
  "lagos-uk": "Lagos → UK",
  "lagos-us": "Lagos → US",
  "lagos-canada": "Lagos → Canada",
  clearing: "Clearing only",
  haulage: "Local haulage",
};
export const routeLabel = (slug: string) =>
  ROUTE_LABEL[slug] ?? slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const naira = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 });
export const ngn = (n: number) => naira.format(n || 0);

// API timestamps are naive UTC
const asDate = (iso: string) => new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");

export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  return asDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return asDate(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function daysAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = Math.floor((Date.now() - asDate(iso).getTime()) / 86_400_000);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
}
