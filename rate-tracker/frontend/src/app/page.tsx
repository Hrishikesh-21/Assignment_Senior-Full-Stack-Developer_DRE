import LatestRatesTable from "@/components/LatestRatesTable";
import HistoryChart from "@/components/HistoryChart";

export default function HomePage() {
  return (
    <main className="page">
      <div className="page-header">
        <h1>Rate Tracker</h1>
        <p>Live provider rates, refreshed automatically every 60 seconds.</p>
      </div>

      <LatestRatesTable />
      <HistoryChart />
    </main>
  );
}
