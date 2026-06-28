"use client";

import { useMemo, useState } from "react";
import { Rate } from "@/types/rate";
import { ApiError, fetchLatestRates } from "@/lib/api";
import { useAutoRefresh } from "@/lib/useAutoRefresh";

type SortKey = "provider" | "rate_value" | "updated_at";
type SortDirection = "asc" | "desc";

const REFRESH_INTERVAL_MS = 60_000;

export default function LatestRatesTable() {
  const [rates, setRates] = useState<Rate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("provider");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const loadRates = async () => {
    try {
      const data = await fetchLatestRates();
      setRates(data);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load latest rates.");
    } finally {
      setLoading(false);
    }
  };

  useAutoRefresh(loadRates, REFRESH_INTERVAL_MS);

  const sortedRates = useMemo(() => {
    if (!rates) return [];
    const sorted = [...rates].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "provider") {
        cmp = a.provider.name.localeCompare(b.provider.name);
      } else if (sortKey === "rate_value") {
        cmp = parseFloat(a.rate_value) - parseFloat(b.rate_value);
      } else {
        cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [rates, sortKey, sortDirection]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  const sortArrow = (key: SortKey) => (key === sortKey ? (sortDirection === "asc" ? "▲" : "▼") : "");

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Latest Rates</h2>
        <div className="status-row">
          <span className="dot" />
          Auto-refreshing every 60s
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!error && (
        <table>
          <thead>
            <tr>
              <th onClick={() => handleSort("provider")}>
                Provider <span className="sort-arrow">{sortArrow("provider")}</span>
              </th>
              <th>Rate Type</th>
              <th onClick={() => handleSort("rate_value")}>
                Rate <span className="sort-arrow">{sortArrow("rate_value")}</span>
              </th>
              <th>Effective Date</th>
              <th onClick={() => handleSort("updated_at")}>
                Last Updated <span className="sort-arrow">{sortArrow("updated_at")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="skeleton-row">
                  <td colSpan={5}>&nbsp;</td>
                </tr>
              ))}

            {!loading && sortedRates.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <div className="empty-state">No rates available yet.</div>
                </td>
              </tr>
            )}

            {!loading &&
              sortedRates.map((rate) => (
                <tr key={rate.id}>
                  <td>{rate.provider.name}</td>
                  <td>{rate.rate_type.code}</td>
                  <td>{parseFloat(rate.rate_value).toFixed(2)}%</td>
                  <td>{rate.effective_date}</td>
                  <td>{new Date(rate.updated_at).toLocaleString()}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
