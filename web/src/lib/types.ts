import type { components, paths } from "@/lib/types.generated";

export type CatalogItem = {
  id: string;
  slug: string;
  name: string;
  aliases?: string[];
  make_id?: string;
  model_id?: string;
  generation_id?: string;
  year_from?: number | null;
  year_to?: number | null;
};

export type CatalogModification = CatalogItem & {
  source?: { name: string; id: string | null; url: string | null } | null;
  specs?: {
    engine_code: string | null;
    frame_code: string | null;
    engine_l: number | null;
    power_hp: number | null;
    fuel: string | null;
    transmission: string | null;
    drive: string | null;
    production_period_raw: string | null;
    summary_raw: string | null;
  } | null;
};

export type CatalogCity = CatalogItem & { region_id: string };

export type User = components["schemas"]["UserOut"];
export type AuthSession = components["schemas"]["AuthSessionResponse"];

export type UserNotification = {
  id: string;
  saved_search_id: string;
  listing_id: string;
  title: string;
  body: string;
  url: string;
  read_at: string | null;
  created_at: string;
};

export type UserNotificationList = {
  items: UserNotification[];
  unread_count: number;
};

export type ConversationParticipant = {
  id: string;
  display_name: string;
};

export type ConversationListing = {
  id: string;
  title: string;
  slug: string;
};

export type ConversationLastMessage = {
  id: string;
  body: string;
  sender_id: string;
  created_at: string;
  read_at: string | null;
};

export type ConversationSummary = {
  id: string;
  listing: ConversationListing;
  buyer_id: string;
  seller_id: string;
  participants: ConversationParticipant[];
  last_message: ConversationLastMessage | null;
  last_message_at: string | null;
  unread_count: number;
  blocked_by_me: boolean;
  is_blocked: boolean;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  created_at: string;
  read_at: string | null;
};

export const MAX_CONVERSATION_MESSAGE_LENGTH = 2000;

export type ConversationThread = {
  conversation: ConversationSummary;
  messages: ConversationMessage[];
  has_more: boolean;
  next_before_sequence: number | null;
};

export type Seller = { type: "private" | "company"; id: string; name: string; slug?: string };
export type Money = {
  amount: string;
  currency: "BYN" | "USD";
  display_amount?: string | null;
  display_currency?: "BYN" | "USD" | null;
  display_byn?: string | null;
  rate_date?: string | null;
};

export type ListingSummary = {
  id: string;
  slug: string;
  title: string;
  make: CatalogItem | null;
  model: CatalogItem | null;
  generation?: CatalogItem | null;
  year: number | null;
  mileage_km: number | null;
  fuel: string | null;
  transmission: string | null;
  drive: string | null;
  body_type?: string | null;
  body_variant_id?: string | null;
  body_variant?: CatalogItem | null;
  price: Money | null;
  region: CatalogItem | null;
  city: CatalogItem | null;
  manual_city?: string | null;
  cover_url?: string | null;
  photo_urls?: string[];
  seller: Seller;
  created_at: string;
  updated_at: string;
  damaged: boolean;
  parts_only: boolean;
};

export type Listing = ListingSummary & {
  status: "draft" | "pending_review" | "rejected" | "active" | "paused" | "sold" | "archived" | "blocked";
  revision: number;
  moderation_reason?: string | null;
  modification_id?: string | null;
  modification?: CatalogModification | null;
  description: string;
  engine_volume_l?: string | null;
  power_hp?: number | null;
  condition: string | null;
  vin?: string | null;
  photo_urls: string[];
  photos?: ListingPhoto[];
  contact_phone?: string;
  phone?: string;
  color?: string | null;
  customs_status?: string | null;
  technical_condition?: string | null;
  body_condition?: string | null;
  exchange?: boolean | null;
  bargaining?: boolean | null;
  credit?: boolean | null;
  leasing?: boolean | null;
  equipment?: string[];
  district?: string | null;
  call_hours?: string | null;
};

export type ListingPhoto = {
  id: string;
  url?: string | null;
  status: "queued" | "processing" | "ready" | "failed" | string;
  position: number;
  is_cover: boolean;
  error?: string;
};

export type ListResponse<T> = {
  items: T[];
  pagination?: { page: number; page_size: number; total: number; pages: number };
};

export type Company = Omit<components["schemas"]["PrivateCompanyOut"], "status"> & {
  status: "pending" | "approved" | "rejected" | "blocked";
};

export type CompanySummary = Omit<components["schemas"]["PublicCompanyOut"], "status"> & {
  status: "pending" | "approved" | "rejected" | "blocked";
  listing_count?: number;
};

export type Report = {
  id: string;
  listing_id?: string;
  category: ReportCategory;
  comment: string;
  status: string;
  created_at?: string;
};

export type ReportCategory = components["schemas"]["ReportInput"]["category"];

export type ApiErrorShape = components["schemas"]["ApiErrorOut"];

export type ListingSearch = {
  q?: string;
  make_id?: string;
  model_id?: string;
  generation_id?: string;
  modification_id?: string;
  body_variant_id?: string;
  price_min?: string;
  price_max?: string;
  currency?: string;
  year_min?: string;
  year_max?: string;
  mileage_min?: string;
  mileage_max?: string;
  fuel?: string;
  transmission?: string;
  drive?: string;
  body_type?: string;
  damaged?: string;
  parts_only?: string;
  condition?: string;
  color?: string;
  customs_status?: string;
  technical_condition?: string;
  body_condition?: string;
  exchange?: string;
  bargaining?: string;
  credit?: string;
  leasing?: string;
  equipment?: string[];
  district?: string;
  call_hours?: string;
  has_vin?: string;
  has_photos?: string;
  engine_volume_min?: string;
  engine_volume_max?: string;
  power_min?: string;
  power_max?: string;
  region_id?: string;
  city_id?: string;
  seller_type?: string;
  page?: string;
  page_size?: string;
  sort?: "newest" | "price_asc" | "price_desc" | "year_desc" | "mileage_asc";
};

type ListingDraftApiInput =
  paths["/api/v1/listings/drafts"]["post"]["requestBody"]["content"]["application/json"];

export type ListingDraftInput = Omit<ListingDraftApiInput, "engine_volume_l" | "seller_type"> & {
  seller_type: NonNullable<ListingDraftApiInput["seller_type"]>;
  engine_volume_l?: string | null;
};
