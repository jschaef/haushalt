// Browser-side client for haushalt-api (backend/). Same-origin calls to
// /api/v1/*; app/api/v1/[...path]/route.ts adds the bearer token.

import { reportQuery, type ReportFilter, type ReportGroup, type ReportSource } from "@/lib/report";

export type Category = {
  id: number;
  key: string;
  name_de: string;
  name_en: string;
  // income: only for incoming bank bookings (salary, child benefit)
  kind: "variable" | "fixed" | "income";
  color: string;
  icon: string;
  // counts as food in the purchases overview
  is_food: boolean;
};

// receipts, fixed costs and payments never use an income category
export const spendingCategories = <T extends Pick<Category, "kind">>(list: T[]): T[] => list.filter((c) => c.kind !== "income");

export type Item = {
  id?: number | null;
  name: string;
  quantity: number;
  // what quantity counts (weighed goods: kg)
  unit?: Unit;
  unit_price_cents: number | null;
  // paid: the printed price minus the article's discount
  total_cents: number;
  discount_cents?: number;
  discount_label?: string;
  category_id: number | null;
};

export type Receipt = {
  id: number;
  status: "draft" | "confirmed";
  source: "photo" | "pdf";
  store_name: string;
  purchased_on: string | null;
  // "HH:MM:SS"; time, receipt number and TSE only when printed
  purchased_at: string | null;
  receipt_number: string;
  tse_transaction: string;
  tse_serial: string;
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
  // an upload of a receipt already recorded: this is the existing one
  already_present?: boolean;
};

export type Averages = { day: number; week: number; month: number; year: number };

export type Summary = {
  start: string;
  end: string;
  days: number;
  // the reset date ("ab jetzt"): the dashboard starts there, null = none
  since: string | null;
  receipt_count: number;
  total_cents: number;
  variable_cents: number;
  fixed_cents: number;
  previous_total_cents: number;
  // counted incoming bookings in an income category (refunds lower spending)
  income_cents: number;
  // income minus spending: saved, or still on the accounts
  balance_cents: number;
  savings_rate: number | null;
  // part of the balance moved to own savings accounts
  saved_cents: number;
  // bookings still waiting for review count nowhere yet
  open: { count: number; out_cents: number; in_cents: number };
  // bookings marked as one-off: in no category, average, balance or chart
  one_off: { count: number; out_cents: number; in_cents: number };
  by_income: { key: string; name_de: string; name_en: string; color: string; cents: number }[];
  monthly: { month: string; income_cents: number; spending_cents: number }[];
  average: { total: Averages; variable: Averages; fixed: Averages };
  by_category: { key: string; name_de: string; name_en: string; color: string; kind: string; cents: number }[];
  // tags overlap: no shares, every tag counts the full amount
  by_tag: { id: number; name: string; color: string; cents: number }[];
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
  tag_ids: number[];
  daily_cents: number;
};

export type Tag = { id: number; name: string; color: string };

// without tag_ids an update keeps the tags
export type RecurringBody = Omit<Recurring, "id" | "daily_cents" | "meter_id" | "tag_ids"> & { meter_id?: number | null; tag_ids?: number[] };

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
  account_id: number | null;
  receipt_id: number | null;
  recurring_id: number | null;
  category_id: number | null;
  // ignored: this debit pays the statement of that credit card account
  settles_account_id: number | null;
  // auto: the app decided (matched again after changes), person: kept
  decided_by: "auto" | "person";
  // marked by a person: counted apart from averages and balance
  one_off: boolean;
  tag_ids: number[];
};

// a word in a bank counterparty that counts payments in a category
export type Merchant = { id: number; keyword: string; category_id: number };
export type MerchantInput = { keyword: string; category_id: number };
export type ApiToken = { id: number; name: string; hint: string; created_at: string; last_used_at: string | null };
export type NewApiToken = ApiToken & { token: string };

// the household (tenant) of the logged-in member
export type Household = { id: number; name: string };

export type BankSettings = {
  // bookings from this amount on are suggested as one-offs; 0: none
  one_off_threshold_cents: number;
};

export type ImportResult = {
  read: number;
  imported: number;
  duplicates: number;
  // bookings between two own accounts (ignored, they are no spending)
  transfers: number;
  // debits paying a card statement (the card bookings count one by one)
  settlements: number;
  account_id: number | null;
  account_name: string | null;
} & Record<BookingStatus, number>;

// card_number: masked number of a credit card account, "" for other accounts
// kind: transfers to a savings account count as saved; card = a card statement's account
export type BankAccount = {
  id: number;
  name: string;
  bank: string;
  iban: string;
  card_number: string;
  kind: "giro" | "savings" | "card";
  color: string;
  bookings: number;
};
export type BankAccountInput = Pick<BankAccount, "name" | "bank" | "iban" | "color"> & { kind: "giro" | "savings" };

export type ReceiptCandidate = { id: number; store_name: string; purchased_on: string | null; total_cents: number; store_matches: boolean };

export type BookingDecision = {
  status: BookingStatus;
  receipt_id?: number | null;
  recurring_id?: number | null;
  category_id?: number | null;
  tag_ids?: number[];
};

export type User = {
  id: number;
  username: string;
  display_name: string;
  locale: "de" | "en";
  is_admin: boolean;
  disabled: boolean;
  must_change_password: boolean;
  // manages households, belongs to none (sees no household data)
  is_operator: boolean;
};

export type HouseholdAdmin = { id: number; username: string; display_name: string; disabled: boolean };
export type OperatorHousehold = {
  id: number;
  name: string;
  disabled: boolean;
  created_at: string;
  members: number;
  admins: HouseholdAdmin[];
};

export type OneTimePassword = { user: User; one_time_password: string };

export type Store = { id: number; name: string; default_category_id: number | null; receipts: number; total_cents: number };

export type Range = "7d" | "30d" | "90d" | "365d" | "ytd" | "all" | "custom";
// range "custom": YYYY-MM-DD, end empty = today
export type CustomRange = { start: string; end: string };

export type Unit = "piece" | "kg" | "l";

// one product of the purchases overview: equal article texts grouped
export type Product = {
  key: string;
  name: string;
  category_id: number | null;
  is_food: boolean;
  total_cents: number;
  lines: number;
  quantities: Partial<Record<Unit, number>>;
  // average price per piece, kg or l
  average_cents: Partial<Record<Unit, number>>;
  stores: string[];
  last_bought: string;
};

export type Purchases = {
  start: string;
  end: string;
  food_cents: number;
  nonfood_cents: number;
  total_cents: number;
  products: Product[];
};

export type PurchaseFilter = {
  range: Range;
  custom: CustomRange;
  food: "all" | "food" | "nonfood";
  store_id: number | null;
  category_id: number | null;
  q: string;
};

// one entry of the report: a receipt line, a bank booking or one month of a
// fixed cost; spending is positive (a refund negative), income its own flow
export type ReportEntry = {
  source: ReportSource;
  date: string;
  // fixed costs: the end of the month slice
  until: string | null;
  cents: number;
  flow: "spending" | "income";
  text: string;
  detail: string;
  category_id: number | null;
  tag_ids: number[];
  store_id: number | null;
  account_id: number | null;
  one_off: boolean;
  receipt_id: number | null;
  transaction_id: number | null;
  recurring_id: number | null;
  // the part of a receipt its lines do not explain
  rest: boolean;
};

// key: "2026-10" (month), an id (category, tag, account), a name (store) or a source; null = none
export type ReportGroupRow = { key: string | number | null; spending_cents: number; income_cents: number; count: number };

export type Report = {
  start: string;
  end: string;
  spending_cents: number;
  income_cents: number;
  balance_cents: number;
  count: number;
  groups: ReportGroupRow[];
  // the newest 500; the CSV export holds all
  entries: ReportEntry[];
  truncated: boolean;
};

export type ProductLine = {
  receipt_id: number;
  purchased_on: string;
  store_name: string;
  name: string;
  quantity: number;
  unit: Unit;
  total_cents: number;
  discount_cents: number;
};

function periodQuery(range: Range, custom: CustomRange): URLSearchParams {
  const params = new URLSearchParams({ range });
  if (range === "custom") {
    params.set("start", custom.start);
    if (custom.end) params.set("end", custom.end);
  }
  return params;
}

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

// A page fires several requests at once; when they all answer 401 or 403,
// only the first may navigate - every further assignment would abort the
// navigation already under way.
let leaving = false;

function leaveTo(url: string) {
  if (leaving) return;
  leaving = true;
  window.location.href = url;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { cache: "no-store", ...init });
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("setup")) {
    // session expired or revoked: back to the login, keep the place
    leaveTo(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError(401, "Not logged in");
  }
  if (!response.ok) {
    const error = errorFrom(response.status, await response.json().catch(() => ({})), response.statusText);
    if (error.message === "operator_only" && typeof window !== "undefined") {
      // the operator has no household: its own page
      leaveTo("/operator");
    }
    if (error.message === "password_change_required" && typeof window !== "undefined") {
      // logged in with a one-time password: replace it first
      leaveTo(`/password?next=${encodeURIComponent(window.location.pathname)}`);
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
  household: () => request<Household>("household"),
  operator: {
    households: () => request<OperatorHousehold[]>("operator/households"),
    create: (body: { name: string; admin_username: string; admin_display_name?: string }) =>
      request<{ household: OperatorHousehold; one_time_password: string }>("operator/households", json("POST", body)),
    update: (id: number, body: { name?: string; disabled?: boolean }) =>
      request<OperatorHousehold>(`operator/households/${id}`, json("PATCH", body)),
    resetAdmin: (userId: number) => request<{ one_time_password: string }>(`operator/users/${userId}/reset-password`, { method: "POST" }),
  },
  // admins only
  renameHousehold: (name: string) => request<Household>("household", json("PUT", { name })),
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
  tags: () => request<Tag[]>("tags"),
  createTag: (body: Omit<Tag, "id">) => request<Tag>("tags", json("POST", body)),
  updateTag: (id: number, body: Omit<Tag, "id">) => request<Tag>(`tags/${id}`, json("PUT", body)),
  deleteTag: (id: number) => request<void>(`tags/${id}`, { method: "DELETE" }),
  receipts: (status?: "draft" | "confirmed") => request<Receipt[]>(status ? `receipts?status=${status}` : "receipts"),
  receipt: (id: number) => request<Receipt>(`receipts/${id}`),
  upload: (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<Receipt[]>("receipts", { method: "POST", body: form });
  },
  updateReceipt: (
    id: number,
    patch: Partial<Pick<Receipt, "purchased_on" | "purchased_at" | "receipt_number" | "total_cents" | "items">> & { store_name?: string },
  ) =>
    request<Receipt>(`receipts/${id}`, json("PATCH", patch)),
  confirmReceipt: (id: number) => request<Receipt>(`receipts/${id}/confirm`, { method: "POST" }),
  rereadReceipt: (id: number) => request<Receipt>(`receipts/${id}/reread`, { method: "POST" }),
  deleteReceipt: (id: number) => request<void>(`receipts/${id}`, { method: "DELETE" }),
  fileUrl: (id: number) => `/api/v1/receipts/${id}/file`,
  recurring: () => request<Recurring[]>("recurring"),
  createRecurring: (body: RecurringBody) => request<Recurring>("recurring", json("POST", body)),
  updateRecurring: (id: number, body: RecurringBody) =>
    request<Recurring>(`recurring/${id}`, json("PUT", body)),
  deleteRecurring: (id: number) => request<void>(`recurring/${id}`, { method: "DELETE" }),
  summary: (range: Range, custom?: CustomRange) =>
    request<Summary>(
      range === "custom" && custom
        ? `stats/summary?range=custom&start=${encodeURIComponent(custom.start)}${custom.end ? `&end=${encodeURIComponent(custom.end)}` : ""}`
        : `stats/summary?range=${range}`,
    ),
  resetDate: () => request<{ since: string | null }>("stats/since"),
  purchases: (filter: PurchaseFilter) => {
    const params = periodQuery(filter.range, filter.custom);
    params.set("food", filter.food);
    if (filter.store_id !== null) params.set("store_id", String(filter.store_id));
    if (filter.category_id !== null) params.set("category_id", String(filter.category_id));
    if (filter.q.trim()) params.set("q", filter.q.trim());
    return request<Purchases>(`purchases?${params}`);
  },
  productLines: (key: string, filter: PurchaseFilter) => {
    const params = periodQuery(filter.range, filter.custom);
    params.set("key", key);
    if (filter.store_id !== null) params.set("store_id", String(filter.store_id));
    return request<ProductLine[]>(`purchases/lines?${params}`);
  },
  report: (filter: ReportFilter, group: ReportGroup) => request<Report>(`report?${reportQuery(filter, group)}`),
  reportCsvUrl: (filter: ReportFilter) => `/api/v1/report/csv?${reportQuery(filter)}`,
  // admins only; null lifts the reset date
  saveResetDate: (since: string | null) => request<{ since: string | null }>("stats/since", json("PUT", { since })),
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
  // without accountId the API takes the account from the statement's IBAN
  importStatement: (file: File, accountId?: number | null) => {
    const form = new FormData();
    form.append("file", file);
    if (accountId) form.append("account_id", String(accountId));
    return request<ImportResult>("bank/import", { method: "POST", body: form });
  },
  accounts: () => request<BankAccount[]>("bank/accounts"),
  createAccount: (body: BankAccountInput) => request<BankAccount>("bank/accounts", json("POST", body)),
  updateAccount: (id: number, body: BankAccountInput) => request<BankAccount>(`bank/accounts/${id}`, json("PUT", body)),
  deleteAccount: (id: number) => request<void>(`bank/accounts/${id}`, { method: "DELETE" }),
  // all bookings (the API returns the newest 500 without a limit)
  transactions: (status?: BookingStatus) =>
    request<BankTransaction[]>(status ? `bank/transactions?status=${status}&limit=20000` : "bank/transactions?limit=20000"),
  candidates: (id: number) => request<ReceiptCandidate[]>(`bank/transactions/${id}/candidates`),
  decide: (id: number, decision: BookingDecision) => request<BankTransaction>(`bank/transactions/${id}`, json("PATCH", decision)),
  rematch: () => request<{ matched: number }>("bank/rematch", { method: "POST" }),
  markOneOff: (id: number, oneOff: boolean) =>
    request<BankTransaction>(`bank/transactions/${id}/one-off`, json("PUT", { one_off: oneOff })),
  bankSettings: () => request<BankSettings>("bank/settings"),
  merchants: () => request<Merchant[]>("bank/merchants"),
  createMerchant: (body: MerchantInput) => request<Merchant>("bank/merchants", json("POST", body)),
  updateMerchant: (id: number, body: MerchantInput) => request<Merchant>(`bank/merchants/${id}`, json("PUT", body)),
  deleteMerchant: (id: number) => request<void>(`bank/merchants/${id}`, { method: "DELETE" }),
  apiTokens: () => request<ApiToken[]>("api-tokens"),
  createApiToken: (name: string) => request<NewApiToken>("api-tokens", json("POST", { name })),
  revokeApiToken: (id: number) => request<void>(`api-tokens/${id}`, { method: "DELETE" }),
  saveBankSettings: (body: BankSettings) => request<BankSettings>("bank/settings", json("PUT", body)),
  deleteTransaction: (id: number) => request<void>(`bank/transactions/${id}`, { method: "DELETE" }),
};
