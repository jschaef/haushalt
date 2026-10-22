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
  daily_cents: number;
};

export type User = { id: number; username: string; display_name: string; locale: "de" | "en" };

export type Store = { id: number; name: string; default_category_id: number | null; receipts: number; total_cents: number };

export type Range = "7d" | "30d" | "90d" | "365d" | "ytd" | "all";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
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
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  me: () => request<User>("me"),
  updateMe: (patch: Partial<Pick<User, "display_name" | "locale">> & { password?: string }) =>
    request<User>("me", json("PATCH", patch)),
  users: () => request<User[]>("users"),
  addUser: (body: { username: string; password: string; display_name?: string }) =>
    request<User>("users", json("POST", body)),
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
  createRecurring: (body: Omit<Recurring, "id" | "daily_cents">) => request<Recurring>("recurring", json("POST", body)),
  updateRecurring: (id: number, body: Omit<Recurring, "id" | "daily_cents">) =>
    request<Recurring>(`recurring/${id}`, json("PUT", body)),
  deleteRecurring: (id: number) => request<void>(`recurring/${id}`, { method: "DELETE" }),
  summary: (range: Range) => request<Summary>(`stats/summary?range=${range}`),
};
