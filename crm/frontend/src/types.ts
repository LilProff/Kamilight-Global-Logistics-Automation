export type Status = "new" | "quoted" | "booked" | "repeat" | "vip" | "dormant" | "lost";
export type CustomerType = "individual" | "online_seller" | "business" | "diaspora" | "partner";
export type Channel = "whatsapp" | "email";
export type Category = "marketing" | "utility";

export interface Filters {
  search?: string;
  statuses?: Status[];
  customer_types?: CustomerType[];
  routes_any?: string[];
  tags_any?: string[];
  sources?: string[];
  cities?: string[];
  assigned_to?: string;
  min_shipments?: number | "";
  max_shipments?: number | "";
  min_spend?: number | "";
  max_spend?: number | "";
  shipped_within_days?: number | "";
  not_shipped_for_days?: number | "";
  never_shipped?: boolean;
  opted_in_only?: boolean;
}

export interface Contact {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  company: string;
  city: string;
  customer_type: CustomerType;
  status: Status;
  lost_reason: string;
  source: string;
  routes: string[];
  tags: string[];
  goods: string;
  preferred_mode: string;
  assigned_to: string;
  notes: string;
  birthday: string;
  wa_opt_in: boolean;
  wa_opt_in_at: string | null;
  wa_opted_out: boolean;
  do_not_contact: boolean;
  next_follow_up: string | null;
  shipments_count: number;
  total_spend_ngn: number;
  first_shipment_at: string | null;
  last_shipment_at: string | null;
  last_route: string;
  last_inbound_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimelineEvent {
  id: number;
  kind: string;
  title: string;
  detail: string;
  amount_ngn: number | null;
  created_at: string;
}

export interface ContactDetail extends Contact {
  events: TimelineEvent[];
}

export interface Options {
  statuses: Status[];
  customer_types: CustomerType[];
  sources: string[];
  routes: string[];
  tags: string[];
  cities: string[];
  staff: string[];
}

export interface Segment {
  id: number;
  name: string;
  description: string;
  filters: Filters;
  count: number;
  created_at: string;
}

export interface Preview {
  matched: number;
  will_receive: number;
  excluded: Record<string, number>;
  fee_per_message_ngn: number;
  estimated_cost_ngn: number;
  test_mode: boolean;
}

export interface Report {
  total: number;
  queued: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  skipped: number;
  replied: number;
  estimated_cost_ngn: number;
}

export interface Campaign {
  id: number;
  name: string;
  channel: Channel;
  category: Category;
  status: "draft" | "scheduled" | "sending" | "sent" | "cancelled";
  filters: Filters;
  segment_id: number | null;
  subject: string;
  body: string;
  media_url: string;
  media_type: "" | "image" | "video" | "document";
  wa_template_name: string;
  wa_template_lang: string;
  wa_template_params: string[];
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  test_mode: boolean;
  created_at: string;
  report: Report;
  audience?: Preview | null;
}

export interface Stats {
  total: number;
  by_status: Partial<Record<Status, number>>;
  marketing_consent: number;
  opted_out: number;
  new_last_30d: number;
  campaigns_last_30d: number;
  messages_sent_30d: number;
  replies_30d: number;
  channels: { whatsapp: boolean; email: boolean };
}
