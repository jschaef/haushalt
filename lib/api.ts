// Browser-side client for haushalt-api (backend/). Same-origin calls to
// /api/v1/*; app/api/v1/[...path]/route.ts adds the bearer token.

export type Category = {
  id: number;
  key: string;
  name_de: string;
  name_en: string;
  kind: "variable" | "fixed";
  color: string;
  icon: string;
};

export type Item = {
  id?: number | null;
  name: string;
  quantity: number;
  unit_price_cents: number | null;
  total_cents: number;
  category_id: number | null;
};

export type Receipt = {
  id: number;
  status: "draft" | "confirmed";
  source: "photo" | "pdf";
  store_name: string;
  purchased_on: string | null;
  total_cents: number;
  currency: string;
  payment_method: string;
  file_name: string;
  media_type: string;
  error: string;
  uploaded_by: number;
  items: Item[];
  item_sum_cents: number;
  duplicates: number[];
  // photo/PDF deleted after the retention period (data stays)
  file_deleted: boolean;
};

export type Averages = { day: number; week: number; month: number; year: number };

export type Summary = {
  start: string;
  end: string;
  days: number;
  receipt_count: number;
  total_cents: number;
  variable_cents: number;
  fixed_cents: number;
  previous_total_cents: number;
  average: { total: Averages; variable: Averages; fixed: Averages };
  by_category: { key: string; name_de: string; name_en: string; color: string; kind: string; cents: number }[];
  by_store: { name: string; cents: number; count: number }[];
  daily: { date: string; cents: number }[];
};

export type Recurring = {
  id: number;
  name: string;
  category_id: number | null;
  amount_cents: number;
  interval_months: number;
  start_on: string;
  end_on: string | null;
  meter_id: number | null;
  daily_cents: number;
};

export type UtilityKind = "electricity" | "gas" | "water" | "heat" | "other";

export type Meter = {
  id: number;
  name: string;
  kind: UtilityKind;
  unit: string;
  meter_number: string;
  category_id: number | null;
  last_reading: { read_on: string; value: number } | null;
  has_device_token: boolean;
  source_url: string;
  source_path: string;
  last_ingest_at: string | null;
  last_ingest_error: string;
};

export type SourcePreset = { url: string; path: string };

export type MeterReading = { id: number; read_on: string; value: number; source: "manual" | "photo" | "bill" | "device" };

export type Tariff = { id: number; valid_from: string; unit_price_ct: number; base_fee_monthly_cents: number };

export type MeterSummary = {
  meter_id: number;
  period_start: string;
  period_end: string;
  covered_start: string | null;
  covered_end: string | null;
  consumption: number;
  per_day: number | null;
  projected_consumption: number | null;
  projected_cost_cents: number | null;
  paid_cents: number;
  // positive: credit expected, negative: additional payment
  projected_balance_cents: number | null;
  suggested_instalment_cents: number | null;
  intervals: { start: string; end: string; per_day: number }[];
  elapsed_days: number;
};

export type MeterPhotoResult = {
  is_meter: boolean;
  kind: UtilityKind;
  value: number;
  unit: string;
  meter_number: string;
  meter_id: number | null;
  read_on: string;
};

export type UtilityBill = {
  id: number;
  meter_id: number | null;
  kind: UtilityKind;
  provider: string;
  meter_number: string;
  period_start: string | null;
  period_end: string | null;
  consumption: number | null;
  unit: string;
  total_cents: number | null;
  paid_cents: number | null;
  balance_cents: number | null;
  unit_price_ct: number | null;
  base_fee_monthly_cents: number | null;
  new_instalment_cents: number | null;
  file_name: string;
  media_type: string;
  error: string;
};

type MeterInput = Pick<Meter, "name" | "kind" | "unit" | "meter_number" | "category_id">;

export type BookingStatus = "review" | "receipt" | "fixed" | "counted" | "ignored";

export type BankTransaction = {
  id: number;
  booked_on: string;
  // negative: money going out
  amount_cents: number;
  currency: string;
  counterparty: string;
  iban: string;
  purpose: string;
  status: BookingStatus;
  receipt_id: number | null;
  recurring_id: number | null;
  category_id: number | null;
};

export type ImportResult = { read: number; imported: number; duplicates: number } & Record<BookingStatus, number>;

export type ReceiptCandidate = { id: number; store_name: string; purchased_on: string | null; total_cents: number; store_matches: boolean };

export type BookingDecision = {
  status: BookingStatus;
  receipt_id?: number | null;
  recurring_id?: number | null;
  category_id?: number | null;
};

export type User = {
  id: number;
  username: string;
  display_name: string;
  locale: "de" | "en";
  is_admin: boolean;
  disabled: boolean;
  must_change_password: boolean;
};

export type OneTimePassword = { user: User; one_time_password: string };

export type Store = { id: number; name: string; default_category_id: number | null; receipts: number; total_cents: number };

export type Range = "7d" | "30d" | "90d" | "365d" | "ytd" | "all";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    // codes for the UI, e.g. the reasons of a rejected password
    public reasons: string[] = [],
  ) {
    super(message);
  }
}

// FastAPI answers {detail: "text"} or {detail: {code, reasons}}
export function errorFrom(status: number, body: { detail?: unknown }, fallback: string): ApiError {
  const detail = body.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (detail && typeof detail === "object" && "code" in detail) {
    const { code, reasons } = detail as { code: unknown; reasons?: unknown };
    return new ApiError(status, String(code), Array.isArray(reasons) ? reasons.map(String) : []);
  }
  return new ApiError(status, fallback);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { cache: "no-store", ...init });
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("setup")) {
    // session expired or revoked: back to the login, keep the place
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "Not logged in");
  }
  if (!response.ok) {
    const error = errorFrom(response.status, await response.json().catch(() => ({})), response.statusText);
    if (error.message === "password_change_required" && typeof window !== "undefined") {
      // logged in with a one-time password: replace it first
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = `/password?next=${encodeURIComponent(window.location.pathname)}`;
    }
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  me: () => request<User>("me"),
  updateMe: (patch: Partial<Pick<User, "display_name" | "locale">>) => request<User>("me", json("PATCH", patch)),
  users: () => request<User[]>("users"),
  addUser: (body: { username: string; display_name?: string; is_admin?: boolean }) =>
    request<OneTimePassword>("users", json("POST", body)),
  resetPassword: (id: number) => request<OneTimePassword>(`users/${id}/reset-password`, { method: "POST" }),
  updateUser: (id: number, patch: Partial<Pick<User, "display_name" | "is_admin" | "disabled">>) =>
    request<User>(`users/${id}`, json("PATCH", patch)),
  categories: () => request<Category[]>("categories"),
  createCategory: (body: Omit<Category, "id">) => request<Category>("categories", json("POST", body)),
  updateCategory: (id: number, body: Omit<Category, "id">) => request<Category>(`categories/${id}`, json("PUT", body)),
  stores: () => request<Store[]>("stores"),
  receipts: (status?: "draft" | "confirmed") => request<Receipt[]>(status ? `receipts?status=${status}` : "receipts"),
  receipt: (id: number) => request<Receipt>(`receipts/${id}`),
  upload: (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<Receipt[]>("receipts", { method: "POST", body: form });
  },
  updateReceipt: (id: number, patch: Partial<Pick<Receipt, "purchased_on" | "total_cents" | "items">> & { store_name?: string }) =>
    request<Receipt>(`receipts/${id}`, json("PATCH", patch)),
  confirmReceipt: (id: number) => request<Receipt>(`receipts/${id}/confirm`, { method: "POST" }),
  rereadReceipt: (id: number) => request<Receipt>(`receipts/${id}/reread`, { method: "POST" }),
  deleteReceipt: (id: number) => request<void>(`receipts/${id}`, { method: "DELETE" }),
  fileUrl: (id: number) => `/api/v1/receipts/${id}/file`,
  recurring: () => request<Recurring[]>("recurring"),
  createRecurring: (body: Omit<Recurring, "id" | "daily_cents" | "meter_id"> & { meter_id?: number | null }) => request<Recurring>("recurring", json("POST", body)),
  updateRecurring: (id: number, body: Omit<Recurring, "id" | "daily_cents" | "meter_id"> & { meter_id?: number | null }) =>
    request<Recurring>(`recurring/${id}`, json("PUT", body)),
  deleteRecurring: (id: number) => request<void>(`recurring/${id}`, { method: "DELETE" }),
  summary: (range: Range) => request<Summary>(`stats/summary?range=${range}`),
  meters: () => request<Meter[]>("meters"),
  createMeter: (body: MeterInput) => request<Meter>("meters", json("POST", body)),
  updateMeter: (id: number, body: MeterInput) => request<Meter>(`meters/${id}`, json("PUT", body)),
  deleteMeter: (id: number) => request<void>(`meters/${id}`, { method: "DELETE" }),
  sourcePresets: () => request<Record<string, SourcePreset>>("meters/sources/presets"),
  createDeviceToken: (id: number) => request<{ token: string }>(`meters/${id}/device-token`, { method: "POST" }),
  revokeDeviceToken: (id: number) => request<void>(`meters/${id}/device-token`, { method: "DELETE" }),
  setSource: (id: number, body: { source_url: string; source_path: string }) =>
    request<{ source_url: string; source_path: string }>(`meters/${id}/source`, json("PUT", body)),
  pollMeter: (id: number) => request<{ read_on: string; value: number }>(`meters/${id}/poll`, { method: "POST" }),
  meterSummary: (id: number) => request<MeterSummary>(`meters/${id}/summary`),
  readings: (meterId: number) => request<MeterReading[]>(`meters/${meterId}/readings`),
  addReading: (meterId: number, body: Omit<MeterReading, "id">) =>
    request<MeterReading>(`meters/${meterId}/readings`, json("POST", body)),
  deleteReading: (id: number) => request<void>(`readings/${id}`, { method: "DELETE" }),
  readMeterPhoto: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<MeterPhotoResult>("meters/read-photo", { method: "POST", body: form });
  },
  tariffs: (meterId: number) => request<Tariff[]>(`meters/${meterId}/tariffs`),
  addTariff: (meterId: number, body: Omit<Tariff, "id">) => request<Tariff>(`meters/${meterId}/tariffs`, json("POST", body)),
  deleteTariff: (id: number) => request<void>(`tariffs/${id}`, { method: "DELETE" }),
  bills: () => request<UtilityBill[]>("bills"),
  uploadBill: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UtilityBill>("bills", { method: "POST", body: form });
  },
  assignBill: (id: number, meterId: number | null) => request<UtilityBill>(`bills/${id}`, json("PATCH", { meter_id: meterId })),
  applyBill: (id: number) => request<{ tariff: boolean; instalment: boolean }>(`bills/${id}/apply`, { method: "POST" }),
  deleteBill: (id: number) => request<void>(`bills/${id}`, { method: "DELETE" }),
  billFileUrl: (id: number) => `/api/v1/bills/${id}/file`,
  importStatement: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportResult>("bank/import", { method: "POST", body: form });
  },
  transactions: (status?: BookingStatus) =>
    request<BankTransaction[]>(status ? `bank/transactions?status=${status}` : "bank/transactions"),
  candidates: (id: number) => request<ReceiptCandidate[]>(`bank/transactions/${id}/candidates`),
  decide: (id: number, decision: BookingDecision) => request<BankTransaction>(`bank/transactions/${id}`, json("PATCH", decision)),
  rematch: () => request<{ matched: number }>("bank/rematch", { method: "POST" }),
  deleteTransaction: (id: number) => request<void>(`bank/transactions/${id}`, { method: "DELETE" }),
};
