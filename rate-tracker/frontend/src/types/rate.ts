export interface Provider {
  id: number;
  name: string;
}

export interface RateType {
  id: number;
  code: string;
}

export interface Rate {
  id: number;
  provider: Provider;
  rate_type: RateType;
  rate_value: string; // DRF serializes DecimalField as a string
  effective_date: string; // ISO date "YYYY-MM-DD"
  ingestion_timestamp: string;
  currency: string | null;
  source_url: string | null;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
