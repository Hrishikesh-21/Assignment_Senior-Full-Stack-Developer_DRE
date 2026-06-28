"""
Generate a synthetic rates_seed.parquet for local development/testing
when the real source file isn't available. Mirrors the real file's
schema discovered during this project's data exploration phase:

    provider: string
    rate_type: string
    rate_value: double
    effective_date: date32[day]
    ingestion_ts: timestamp[us]
    source_url: string
    raw_response_id: string
    currency: string

Deliberately injects the same kinds of messiness found in the real
file (provider casing variance, repeated daily scrapes with different
timestamps, a handful of nulls/out-of-range values) so the ingestion
service can be exercised against realistic conditions without needing
the original file.

Usage:
    python scripts/generate_seed_parquet.py --rows 1000000 --out ../data/rates_seed.parquet
"""
import argparse
import random
import uuid
from datetime import date, datetime, timedelta

import pandas as pd

PROVIDERS = [
    "HSBC", "Hsbc", "hsbc",  # intentional casing variance, mirrors real data
    "Chase", "Wells Fargo", "PNC", "Citibank", "Bank of America",
    "ICICI Bank", "Ally Bank", "Capital One",
]
RATE_TYPES = ["MORTGAGE_30Y", "MORTGAGE_15Y", "ARM_5Y", "SAVINGS_APY", "CD_12M"]
CURRENCIES = ["USD", "usd", "US Dollar"]


def generate(num_rows: int, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    rows = []
    start_date = date(2026, 1, 1)

    for i in range(num_rows):
        provider = random.choice(PROVIDERS)
        rate_type = random.choice(RATE_TYPES)
        effective_date = start_date + timedelta(days=random.randint(0, 180))
        ingestion_ts = datetime(
            effective_date.year, effective_date.month, effective_date.day,
            random.randint(0, 23), random.randint(0, 59),
        )

        rate_value = round(random.uniform(1.5, 8.5), 4)

        # ~0.02% null rate_value, ~0.003% out-of-range — mirrors real ratios.
        if random.random() < 0.0002:
            rate_value = None
        elif random.random() < 0.00003:
            rate_value = random.choice([-1.0, 75.0])

        rows.append({
            "provider": provider,
            "rate_type": rate_type,
            "rate_value": rate_value,
            "effective_date": effective_date,
            "ingestion_ts": ingestion_ts,
            "source_url": f"https://example.com/rates/{provider.lower().replace(' ', '-')}",
            "raw_response_id": str(uuid.uuid4()),
            "currency": random.choice(CURRENCIES),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--out", type=str, default="../data/rates_seed.parquet")
    args = parser.parse_args()

    df = generate(args.rows)
    df.to_parquet(args.out, engine="pyarrow", compression="zstd")
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
