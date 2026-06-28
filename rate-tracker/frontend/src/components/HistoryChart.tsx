"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Rate } from "@/types/rate";
import { ApiError, fetchHistory, fetchLatestRates } from "@/lib/api";
import { useAutoRefresh } from "@/lib/useAutoRefresh";

const REFRESH_INTERVAL_MS = 60_000;
const HISTORY_WINDOW_DAYS = 30;

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function HistoryChart() {
  const [providers, setProviders] = useState<string[]>([]);
  const [rateTypes, setRateTypes] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [selectedRateType, setSelectedRateType] = useState<string>("");
  const [history, setHistory] = useState<Rate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLatestRates()
      .then((rates) => {
        const providerNames = Array.from(new Set(rates.map((r) => r.provider.name))).sort();
        const typeCodes = Array.from(new Set(rates.map((r) => r.rate_type.code))).sort();
        setProviders(providerNames);
        setRateTypes(typeCodes);
        if (providerNames.length && !selectedProvider) setSelectedProvider(providerNames[0]);
        if (typeCodes.length && !selectedRateType) setSelectedRateType(typeCodes[0]);
      })
      .catch(() => {
        /* selector population failure is non-fatal; chart will just show empty state */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadHistory = async () => {
    if (!selectedProvider || !selectedRateType) {
      setLoading(false);
      return;
    }
    try {
      const data = await fetchHistory({
        provider: selectedProvider,
        rate_type: selectedRateType,
        from: isoDaysAgo(HISTORY_WINDOW_DAYS),
        to: new Date().toISOString().slice(0, 10),
        limit: 500,
      });
      setHistory(data.results);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load history.");
    } finally {
      setLoading(false);
    }
  };

  useAutoRefresh(loadHistory, REFRESH_INTERVAL_MS);

  useEffect(() => {
    setLoading(true);
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProvider, selectedRateType]);

  const chartData = useMemo(() => {
    return [...history]
      .sort((a, b) => a.effective_date.localeCompare(b.effective_date))
      .map((r) => ({
        date: r.effective_date,
        rate: parseFloat(r.rate_value),
      }));
  }, [history]);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>30-Day History</h2>
        <div className="controls">
          <select value={selectedProvider} onChange={(e) => setSelectedProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select value={selectedRateType} onChange={(e) => setSelectedRateType(e.target.value)}>
            {rateTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!error && loading && <div className="empty-state">Loading chart…</div>}

      {!error && !loading && chartData.length === 0 && (
        <div className="empty-state">No history available for this selection.</div>
      )}

      {!error && !loading && chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <CartesianGrid stroke="#232838" strokeDasharray="3 3" />
            <XAxis dataKey="date" stroke="#8b92a8" fontSize={11} />
            <YAxis stroke="#8b92a8" fontSize={11} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#131722", border: "1px solid #232838", fontSize: 12 }}
            />
            <Line type="monotone" dataKey="rate" stroke="#4f8cff" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
