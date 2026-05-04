import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import StockSearchPanel from "../components/StockSearchPanel";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import api from "../api/client";
import type { SnapshotSummary, Holding, EvolutionPoint, CurrentPrices, LiveHolding, Transaction } from "../api/types";
import { useChartColors } from "../context/ThemeContext";

const PIE_COLORS = [
  "#22c55e", "#3b82f6", "#f59e0b", "#a78bfa", "#f87171",
  "#34d399", "#60a5fa", "#fbbf24", "#c084fc", "#fb923c",
  "#2dd4bf", "#818cf8", "#e879f9", "#4ade80", "#38bdf8",
];

const SEMAPHORE_COLORS: Record<string, string> = {
  GO:      "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
  PARTIAL: "bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 border-yellow-500/30",
  WAIT:    "bg-orange-500/20 text-orange-600 dark:text-orange-400 border-orange-500/30",
  ABORT:   "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
};
const SEMAPHORE_ICONS: Record<string, string> = {
  GO: "🟢", PARTIAL: "🟡", WAIT: "🟠", ABORT: "🔴",
};

function MetricCard({ label, value, sub, color = "text-gray-900 dark:text-white" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 dark:text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function fmt(n: number) {
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function DonutChart({ holdings, period }: { holdings: Holding[]; period: string }) {
  const { svgStroke } = useChartColors();
  const sorted = [...holdings].sort((a, b) => Number(b.market_value) - Number(a.market_value));
  const total = sorted.reduce((s, h) => s + Number(h.market_value), 0);
  const cx = 100, cy = 100, r = 80, ir = 52;

  let cumDeg = -90;
  const slices = sorted.map((h, i) => {
    const pct = Number(h.market_value) / total;
    const deg = pct * 360;
    const start = cumDeg;
    cumDeg += deg;
    const toRad = (d: number) => (d * Math.PI) / 180;
    const x1 = cx + r * Math.cos(toRad(start));
    const y1 = cy + r * Math.sin(toRad(start));
    const x2 = cx + r * Math.cos(toRad(cumDeg));
    const y2 = cy + r * Math.sin(toRad(cumDeg));
    const ix1 = cx + ir * Math.cos(toRad(start));
    const iy1 = cy + ir * Math.sin(toRad(start));
    const ix2 = cx + ir * Math.cos(toRad(cumDeg));
    const iy2 = cy + ir * Math.sin(toRad(cumDeg));
    const large = deg > 180 ? 1 : 0;
    const d = [
      `M ${x1} ${y1}`,
      `A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`,
      `L ${ix2} ${iy2}`,
      `A ${ir} ${ir} 0 ${large} 0 ${ix1} ${iy1}`,
      "Z",
    ].join(" ");
    return { d, color: PIE_COLORS[i % PIE_COLORS.length], symbol: h.symbol };
  });

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 flex flex-col">
      <p className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-3">Distribución — {period.split(" - ")[0]}</p>
      <div className="flex justify-center mb-3">
        <svg width={200} height={200} viewBox="0 0 200 200">
          {slices.map((s) => (
            <path key={s.symbol} d={s.d} fill={s.color} stroke={svgStroke} strokeWidth={1} />
          ))}
        </svg>
      </div>
      <div className="flex flex-col gap-1 overflow-y-auto">
        {sorted.map((h, i) => (
          <div key={h.symbol} className="flex items-center gap-2 text-xs">
            <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
            <span className="font-mono text-gray-700 dark:text-gray-200 w-12 flex-shrink-0">{h.symbol}</span>
            <span className="text-gray-500">{Number(h.weight).toFixed(1)}%</span>
            <span className="text-gray-400 dark:text-gray-600 ml-auto">{fmt(h.market_value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const LIVE_PRICES_INTERVAL_MS = 60_000;

export default function Dashboard() {
  const navigate = useNavigate();
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [liveData, setLiveData] = useState<CurrentPrices | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState<string | undefined>(undefined);
  const chart = useChartColors();

  useEffect(() => {
    Promise.all([
      api.get<SnapshotSummary[]>("/snapshots/"),
      api.get<EvolutionPoint[]>("/snapshots/evolution/"),
      api.get("/snapshots/current/"),
    ]).then(([snapshotsRes, evolutionRes, currentRes]) => {
      setSnapshots(snapshotsRes.data);
      setEvolution(evolutionRes.data);
      setHoldings(currentRes.data.holdings ?? []);
      setTransactions(currentRes.data.transactions ?? []);
    }).finally(() => setLoading(false));
  }, []);

  const fetchLivePrices = () => {
    setLiveLoading(true);
    api.get<CurrentPrices>("/snapshots/current-prices/")
      .then((r) => setLiveData(r.data))
      .catch(() => {/* keep stale data on error */})
      .finally(() => setLiveLoading(false));
  };

  useEffect(() => {
    fetchLivePrices();
    const interval = setInterval(fetchLivePrices, LIVE_PRICES_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const liveMap = new Map<string, LiveHolding>(
    liveData?.holdings.map((h) => [h.symbol, h]) ?? []
  );

  const latest = snapshots[0];
  const prev = snapshots[1];
  const semCode = latest?.semaphore_code ?? null;

  const displayTotal = liveData?.total_live_value ?? Number(latest?.total_value ?? 0);
  const totalPnl = liveData
    ? liveData.holdings.reduce((s, h) => s + h.live_pnl, 0)
    : holdings.reduce((s, h) => s + Number(h.unrealized_pnl), 0);
  const costBasisTotal = liveData
    ? liveData.holdings.reduce((s, h) => s + h.cost_basis, 0)
    : holdings.reduce((s, h) => s + Number(h.cost_basis), 0);
  const totalPnlPct = costBasisTotal > 0 ? (totalPnl / costBasisTotal) * 100 : 0;
  const diff = latest && prev
    ? Number(latest.total_value) - Number(prev.total_value)
    : null;

  if (loading) {
    return (
      <div className="p-6 text-gray-500 text-sm">Cargando datos…</div>
    );
  }

  if (!latest) {
    return (
      <div className="p-6 text-gray-500 text-sm">
        No hay datos aún.{" "}
        <Link to="/pipeline" className="text-green-600 dark:text-green-400 hover:underline">
          Subí el primer informe desde Pipeline →
        </Link>
      </div>
    );
  }

  const evolutionForChart = evolution.map((e) => ({
    ...e,
    label: e.period.split(" - ")[0].slice(0, 3),
  }));

  return (
    <div className="p-6 space-y-6">
      {searchOpen && (
        <StockSearchPanel
          onClose={() => { setSearchOpen(false); setSelectedTicker(undefined); }}
          tickers={holdings.sort((a, b) => Number(b.weight) - Number(a.weight)).map((h) => h.symbol)}
          initialTicker={selectedTicker}
          holding={selectedTicker ? holdings.find((h) => h.symbol === selectedTicker) : undefined}
          liveHolding={selectedTicker ? liveMap.get(selectedTicker) : undefined}
          transactions={selectedTicker ? transactions.filter((t) => t.symbol === selectedTicker) : undefined}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between pr-12">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">{latest.period}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSearchOpen(true)}
            className="inline-flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-300 dark:border-gray-700 px-3 py-1.5 rounded-full transition-colors"
          >
            🔍 Buscar ticker
          </button>
          {semCode ? (
            <span className={`inline-flex items-center gap-2 text-sm font-medium px-3 py-1.5 rounded-full border ${SEMAPHORE_COLORS[semCode] ?? ""}`}>
              {SEMAPHORE_ICONS[semCode]} Semáforo: {semCode}
            </span>
          ) : (
            <span className="text-xs text-gray-400 dark:text-gray-600 border border-gray-200 dark:border-gray-800 px-3 py-1.5 rounded-full">
              Sin semáforo
            </span>
          )}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label={liveData ? "Valor Total (live)" : "Valor Total"}
          value={fmt(displayTotal)}
          sub={diff !== null ? `${diff >= 0 ? "↑" : "↓"} ${fmt(Math.abs(diff))} vs ${prev.period.split(" - ")[0]}` : undefined}
          color="text-green-600 dark:text-green-400"
        />
        <MetricCard
          label="Cash"
          value={fmt(latest.cash)}
          sub={`${((Number(latest.cash) / Number(latest.total_value)) * 100).toFixed(1)}% del portfolio`}
        />
        <MetricCard
          label="Dividendos (mes)"
          value={fmt(latest.dividend_income)}
        />
        <MetricCard
          label="P&L No Realizado"
          value={`${totalPnl >= 0 ? "+" : ""}${fmt(totalPnl)}`}
          sub={`${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}%`}
          color={totalPnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}
        />
      </div>

      {/* Charts row: evolution + pie */}
      <div className="grid grid-cols-3 gap-4">
        {/* Evolution line chart */}
        <div className="col-span-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <p className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">Evolución del portfolio</p>
          <p className="text-xs text-gray-400 dark:text-gray-600 mb-4">Click en un punto para ver el detalle del mes</p>
          {evolutionForChart.length > 1 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart
                data={evolutionForChart}
                onClick={(data) => {
                  const id = data?.activePayload?.[0]?.payload?.id;
                  if (id) navigate(`/months/${id}`);
                }}
                style={{ cursor: "pointer" }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis dataKey="label" tick={{ fill: chart.tick, fontSize: 12 }} />
                <YAxis tick={{ fill: chart.tick, fontSize: 12 }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                <Tooltip
                  contentStyle={{ backgroundColor: chart.tooltipBg, border: `1px solid ${chart.tooltipBorder}`, borderRadius: 8 }}
                  labelStyle={{ color: chart.label }}
                  formatter={(v: number) => [fmt(v), ""]}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: chart.legend }} />
                <Line type="monotone" dataKey="total_value" stroke="#22c55e" strokeWidth={2} dot={{ fill: "#22c55e", r: 3 }} name="Valor total" />
                <Line type="monotone" dataKey="invested_capital" stroke="#3b82f6" strokeWidth={2} dot={{ fill: "#3b82f6", r: 3 }} name="Capital invertido" />
                <Line type="monotone" dataKey="dividend_income" stroke="#f59e0b" strokeWidth={1.5} dot={{ fill: "#f59e0b", r: 3 }} name="Dividendos" />
                <Line type="monotone" dataKey="cash" stroke="#6b7280" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="Cash" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-600 py-16 text-center">Se necesitan al menos 2 meses para mostrar la evolución.</p>
          )}
        </div>

        {/* Pie chart — portfolio distribution */}
        {holdings.length > 0 && <DonutChart holdings={holdings} period={latest.period} />}
      </div>

      {/* Holdings table */}
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
          <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Holdings — {latest.period}</p>
          <div className="flex items-center gap-2">
            {liveData && (
              <span className="text-xs text-gray-400 dark:text-gray-600">
                Live · actualizado {new Date(liveData.updated_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
            {liveLoading && <span className="text-xs text-blue-400 animate-pulse">actualizando…</span>}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-200 dark:border-gray-800">
              <th className="px-5 py-3 text-left">Ticker</th>
              <th className="px-5 py-3 text-right">Precio</th>
              <th className="px-5 py-3 text-right">Valor</th>
              <th className="px-5 py-3 text-right">Peso</th>
              <th className="px-5 py-3 text-right">P&L $</th>
              <th className="px-5 py-3 text-right">P&L %</th>
            </tr>
          </thead>
          <tbody>
            {holdings
              .sort((a, b) => Number(b.market_value) - Number(a.market_value))
              .map((h) => {
                const live = liveMap.get(h.symbol);
                const displayValue = live?.current_value ?? Number(h.market_value);
                const displayPnl = live?.live_pnl ?? Number(h.unrealized_pnl);
                const displayPnlPct = live?.live_pnl_pct ?? Number(h.pnl_pct);
                const displayPrice = live?.current_price ?? Number(h.market_price);
                const changePct = live?.price_change_pct ?? 0;
                return (
                  <tr key={h.symbol} className="border-b border-gray-200/50 dark:border-gray-800/50 hover:bg-gray-100/30 dark:hover:bg-gray-800/30 transition-colors">
                    <td className="px-5 py-3">
                    <button
                      onClick={() => { setSelectedTicker(h.symbol); setSearchOpen(true); }}
                      className="font-mono font-medium text-gray-800 dark:text-gray-100 hover:text-green-600 dark:hover:text-green-400 transition-colors underline-offset-2 hover:underline"
                    >
                      {h.symbol}
                    </button>
                  </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className="text-gray-600 dark:text-gray-300 font-mono">{fmt(displayPrice)}</span>
                        {live && live.price_change !== 0 && (
                          <span className={`text-xs font-mono ${changePct >= 0 ? "text-green-600 dark:text-green-400" : "text-red-500 dark:text-red-400"}`}>
                            {changePct >= 0 ? "▲" : "▼"}{Math.abs(changePct).toFixed(2)}%
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right text-gray-600 dark:text-gray-300">{fmt(displayValue)}</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 bg-gray-200 dark:bg-gray-800 rounded-full h-1.5">
                          <div
                            className="bg-green-500 h-1.5 rounded-full"
                            style={{ width: `${Math.min(Number(h.weight), 15) / 15 * 100}%` }}
                          />
                        </div>
                        <span className="text-gray-600 dark:text-gray-300 w-10 text-right">{Number(h.weight).toFixed(1)}%</span>
                      </div>
                    </td>
                    <td className={`px-5 py-3 text-right font-mono ${displayPnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                      {displayPnl >= 0 ? "+" : ""}{fmt(displayPnl)}
                    </td>
                    <td className={`px-5 py-3 text-right font-mono ${displayPnlPct >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                      {displayPnlPct >= 0 ? "+" : ""}{Number(displayPnlPct).toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
