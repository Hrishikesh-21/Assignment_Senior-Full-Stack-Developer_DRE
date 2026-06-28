import { PaginatedResponse, Rate } from "@/types/rate";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export async function fetchLatestRates(params?: {
  provider?: string;
  rate_type?: string;
}): Promise<Rate[]> {
  const query = new URLSearchParams();
  if (params?.provider) query.set("provider", params.provider);
  if (params?.rate_type) query.set("rate_type", params.rate_type);

  const response = await fetch(`${API_BASE_URL}/rates/latest?${query.toString()}`, {
    cache: "no-store",
  });
  return handleResponse<Rate[]>(response);
}

export async function fetchHistory(params: {
  provider?: string;
  rate_type?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<Rate>> {
  const query = new URLSearchParams();
  if (params.provider) query.set("provider", params.provider);
  if (params.rate_type) query.set("rate_type", params.rate_type);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));

  const response = await fetch(`${API_BASE_URL}/rates/history?${query.toString()}`, {
    cache: "no-store",
  });
  return handleResponse<PaginatedResponse<Rate>>(response);
}
