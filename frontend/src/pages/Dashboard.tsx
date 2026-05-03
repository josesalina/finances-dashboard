import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import StockSearchPanel from "../components/StockSearchPanel";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import api from "../api/client";
import type { SnapshotSummary, Holding, EvolutionPoint } from "../api/types";

const PIE_COLORS = [
  "#22c55e", "#3b82f6", "#f59e0b", "#a78bfa", "#f87171",
  "#34d399", "#60a5fa", "#fbbf24", "#c084fc", "#fb923c",
  "#2dd4bf", "#818cf8", "#e879f9", "#4ade80", "#38bdf8",
];

const SEMAPHORE_COLORS: Record<string, string> = {
  GO:      "bg-green-500/20 text-green-400 border-green-500/30",
  PARTIAL: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  WAIT:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  ABORT:   "bg-red-500/20 text-red-400 border-red-500/30",
};
const SEMAPHORE_ICONS: Record<string, string> = {
  GO: "🟢", PARTIAL: "🟡", WAIT: "🟠", ABORT: "🔴",
};

function MetricCard({ label, value, sub, color = "text-white" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function fmt(n: number) {
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function DonutChart({ holdings, period }: { holdings: Holding[]; period: string }) {
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
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col">
      <p className="text-sm font-medium text-gray-300 mb-3">Distribución — {period.split(" - ")[0]}</p>
      <div className="flex justify-center mb-3">
        <svg width={200} height={200} viewBox="0 0 200 200">
          {slices.map((s) => (
            <path key={s.symbol} d={s.d} fill={s.color} stroke="#111827" strokeWidth={1} />
          ))}
        </svg>
      </div>
      <div className="flex flex-col gap-1 overflow-y-auto">
        {sorted.map((h, i) => (
          <div key={h.symbol} className="flex items-center gap-2 text-xs">
            <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
            <span className="font-mono text-gray-200 w-12 flex-shrink-0">{h.symbol}</span>
            <span className="text-gray-500">{Number(h.weight).toFixed(1)}%</span>
            <span className="text-gray-600 ml-auto">{fmt(h.market_value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<SnapshotSummary[]>("/snapshots/"),
      api.get<EvolutionPoint[]>("/snapshots/evolution/"),
      api.get("/snapshots/current/"),
    ]).then(([snapshotsRes, evolutionRes, currentRes]) => {
      setSnapshots(snapshotsRes.data);
      setEvolution(evolutionRes.data);
      setHoldings(currentRes.data.holdings ?? []);
    }).finally(() => setLoading(false));
  }, []);

  const latest = snapshots[0];
  const prev = snapshots[1];
  const semCode = latest?.semaphore_code ?? null;

  const totalPnl = holdings.reduce((s, h) => s + Number(h.unrealized_pnl), 0);
  const totalPnlPct = holdings.length
    ? (totalPnl / (Number(latest?.total_value) - totalPnl)) * 100
    : 0;
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
        <Link to="/pipeline" className="text-green-400 hover:underline">
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
          onClose={() => setSearchOpen(false)}
          tickers={holdings.sort((a, b) => Number(b.weight) - Number(a.weight)).map((h) => h.symbol)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">{latest.period}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSearchOpen(true)}
            className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-900 hover:bg-gray-800 border border-gray-700 px-3 py-1.5 rounded-full transition-colors"
          >
            🔍 Buscar ticker
          </button>
          {semCode ? (
            <span className={`inline-flex items-center gap-2 text-sm font-medium px-3 py-1.5 rounded-full border ${SEMAPHORE_COLORS[semCode] ?? ""}`}>
              {SEMAPHORE_ICONS[semCode]} Semáforo: {semCode}
            </span>
          ) : (
            <span className="text-xs text-gray-600 border border-gray-800 px-3 py-1.5 rounded-full">
              Sin semáforo
            </span>
          )}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Valor Total"
          value={fmt(latest.total_value)}
          sub={diff !== null ? `${diff >= 0 ? "↑" : "↓"} ${fmt(Math.abs(diff))} vs ${prev.period.split(" - ")[0]}` : undefined}
          color="text-green-400"
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
          color={totalPnl >= 0 ? "text-green-400" : "text-red-400"}
        />
      </div>

      {/* Charts row: evolution + pie */}
      <div className="grid grid-cols-3 gap-4">
        {/* Evolution line chart */}
        <div className="col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-5">
          <p className="text-sm font-medium text-gray-300 mb-1">Evolución del portfolio</p>
          <p className="text-xs text-gray-600 mb-4">Click en un punto para ver el detalle del mes</p>
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
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 12 }} />
                <YAxis tick={{ fill: "#6b7280", fontSize: 12 }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", border: "1px solid #374151", borderRadius: 8 }}
                  labelStyle={{ color: "#e5e7eb" }}
                  formatter={(v: number) => [fmt(v), ""]}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#9ca3af" }} />
                <Line type="monotone" dataKey="total_value" stroke="#22c55e" strokeWidth={2} dot={{ fill: "#22c55e", r: 3 }} name="Valor total" />
                <Line type="monotone" dataKey="invested_capital" stroke="#3b82f6" strokeWidth={2} dot={{ fill: "#3b82f6", r: 3 }} name="Capital invertido" />
                <Line type="monotone" dataKey="dividend_income" stroke="#f59e0b" strokeWidth={1.5} dot={{ fill: "#f59e0b", r: 3 }} name="Dividendos" />
                <Line type="monotone" dataKey="cash" stroke="#6b7280" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="Cash" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-600 py-16 text-center">Se necesitan al menos 2 meses para mostrar la evolución.</p>
          )}
        </div>

        {/* Pie chart — portfolio distribution */}
        {holdings.length > 0 && <DonutChart holdings={holdings} period={latest.period} />}
      </div>

      {/* Holdings table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <p className="text-sm font-medium text-gray-300">Holdings — {latest.period}</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
              <th className="px-5 py-3 text-left">Ticker</th>
              <th className="px-5 py-3 text-right">Valor</th>
              <th className="px-5 py-3 text-right">Peso</th>
              <th className="px-5 py-3 text-right">P&L $</th>
              <th className="px-5 py-3 text-right">P&L %</th>
            </tr>
          </thead>
          <tbody>
            {holdings
              .sort((a, b) => Number(b.market_value) - Number(a.market_value))
              .map((h) => (
                <tr key={h.symbol} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="px-5 py-3 font-mono font-medium text-gray-100">{h.symbol}</td>
                  <td className="px-5 py-3 text-right text-gray-300">{fmt(h.market_value)}</td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 bg-gray-800 rounded-full h-1.5">
                        <div
                          className="bg-green-500 h-1.5 rounded-full"
                          style={{ width: `${Math.min(Number(h.weight), 15) / 15 * 100}%` }}
                        />
                      </div>
                      <span className="text-gray-300 w-10 text-right">{Number(h.weight).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td className={`px-5 py-3 text-right font-mono ${Number(h.unrealized_pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(h.unrealized_pnl) >= 0 ? "+" : ""}{fmt(h.unrealized_pnl)}
                  </td>
                  <td className={`px-5 py-3 text-right font-mono ${Number(h.pnl_pct) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(h.pnl_pct) >= 0 ? "+" : ""}{Number(h.pnl_pct).toFixed(2)}%
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
