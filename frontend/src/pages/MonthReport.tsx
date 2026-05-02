import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import AdvisorReport from "../components/AdvisorReport";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis,
} from "recharts";
import api from "../api/client";
import type { SnapshotDetail, SemaphoreRun } from "../api/types";

const SEMAPHORE_COLORS: Record<string, string> = {
  GO:      "bg-green-500/20 text-green-400 border-green-500/30",
  PARTIAL: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  WAIT:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  ABORT:   "bg-red-500/20 text-red-400 border-red-500/30",
};

const PIE_COLORS = [
  "#22c55e","#3b82f6","#f59e0b","#8b5cf6","#06b6d4",
  "#f97316","#ec4899","#84cc16","#14b8a6","#a78bfa",
  "#fb923c","#38bdf8","#4ade80","#facc15","#c084fc",
];

function fmt(n: number | string) {
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function round2(n: number) { return Math.round(n * 100) / 100; }

export default function MonthReport() {
  const { id } = useParams<{ id: string }>();
  const [snapshot, setSnapshot] = useState<SnapshotDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [latestRun, setLatestRun] = useState<SemaphoreRun | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadSnapshot = () => {
    if (!id) return;
    setLoading(true);
    api.get<SnapshotDetail>(`/snapshots/${id}/`)
      .then((r) => setSnapshot(r.data))
      .finally(() => setLoading(false));
  };

  const loadLatestRun = () => {
    if (!id) return;
    api.get<SemaphoreRun[]>(`/semaphore-runs/?snapshot_id=${id}`)
      .then((r) => setLatestRun(r.data[0] ?? null));
  };

  useEffect(() => {
    loadSnapshot();
    loadLatestRun();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleRefreshSemaforo = async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      const res = await api.post<SemaphoreRun>("/semaphore-runs/run/", { snapshot_id: Number(id) });
      setLatestRun(res.data);
      loadSnapshot();
    } catch {
      // silently fail — user can retry
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) return <div className="p-6 text-gray-500 text-sm">Cargando…</div>;
  if (!snapshot) return <div className="p-6 text-gray-500 text-sm">Snapshot no encontrado.</div>;

  const semRaw     = snapshot.semaforo_raw as Record<string, unknown> | null;
  const semInfo    = semRaw?.semaforo   as Record<string, unknown> | null;
  const semCode    = (semInfo?.code as string | undefined) ?? snapshot.semaphore_code;
  const mercado    = semRaw?.mercado    as Record<string, Record<string, unknown>> | null;
  const semCredito = semRaw?.credito    as Record<string, unknown> | null;
  const semSectores = semRaw?.sectores  as Record<string, unknown> | null;
  const semTasas   = semRaw?.tasas      as Record<string, unknown> | null;
  const semEmergentes = semRaw?.emergentes as Record<string, unknown> | null;
  const semRazones = semInfo?.razones   as string[] | null;
  const semPuntos  = semInfo?.puntos    as number | undefined;
  const semVix     = semRaw?.vix        as Record<string, unknown> | null;

  // Weights chart data — only holdings with target_weight
  const weightsData = snapshot.holdings
    .filter((h) => h.target_weight !== null)
    .map((h) => ({
      symbol: h.symbol,
      actual: Number(h.weight),
      objetivo: Number(h.target_weight),
    }));

  // Markowitz data
  const markowitzRaw = snapshot.markowitz_raw as Record<string, unknown> | null;
  const orders = (markowitzRaw?.orders as Array<Record<string, unknown>> | undefined) ?? [];

  // Pie chart: optimal weights for primary strategy
  const PRIMARY_STRATEGY = markowitzRaw?.primary_strategy as string | undefined;
  const optimalPortfolios = markowitzRaw?.optimal_portfolios as Record<string, Record<string, unknown>> | undefined;
  const primaryWeights = PRIMARY_STRATEGY && optimalPortfolios
    ? (optimalPortfolios[PRIMARY_STRATEGY]?.weights as Record<string, number> | undefined)
    : undefined;
  const pieData = primaryWeights
    ? Object.entries(primaryWeights)
        .filter(([, w]) => w > 0)
        .sort(([, a], [, b]) => b - a)
        .map(([symbol, weight]) => ({ name: symbol, value: round2(weight) }))
    : [];

  // Strategies scatter (risk vs return)
  const strategiesData = optimalPortfolios
    ? Object.entries(optimalPortfolios).map(([key, v]) => ({
        name: key,
        vol: Number(v.vol ?? 0),
        ret: Number(v.return ?? 0),
        sharpe: Number(v.sharpe ?? 0),
        isPrimary: key === PRIMARY_STRATEGY,
      }))
    : [];

  // Risk individual table
  const riskIndividual = (markowitzRaw?.risk_individual as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <Link to="/dashboard" className="text-gray-500 hover:text-gray-300 text-sm">← Dashboard</Link>
        <span className="text-gray-700">/</span>
        <h2 className="text-xl font-semibold text-white">{snapshot.period}</h2>
        {semCode && (
          <span className={`text-xs px-2.5 py-1 rounded-full border ${SEMAPHORE_COLORS[semCode] ?? ""}`}>
            {semCode}
          </span>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Valor total", value: fmt(snapshot.total_value) },
          { label: "Cash", value: fmt(snapshot.cash) },
          { label: "Dividendos", value: fmt(snapshot.dividend_income) },
          { label: "P&L realizado", value: fmt(snapshot.realized_pnl_net) },
        ].map((c) => (
          <div key={c.label} className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{c.label}</p>
            <p className="text-xl font-bold text-white">{c.value}</p>
          </div>
        ))}
      </div>

      {/* ── MARKOWITZ ─────────────────────────────────────────── */}
      {markowitzRaw && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-5">
          <div>
            <p className="text-sm font-medium text-gray-300">Markowitz — Optimización de portafolio</p>
            <p className="text-xs text-gray-600 mt-0.5">
              Estrategia activa: <span className="text-gray-400">{PRIMARY_STRATEGY ?? "—"}</span>
            </p>
          </div>

          {/* Bar chart + Pie chart */}
          {weightsData.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Actual vs objetivo */}
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Actual vs Objetivo</p>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={weightsData} barCategoryGap="30%">
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="symbol" tick={{ fill: "#6b7280", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#111827", border: "1px solid #374151", borderRadius: 8 }}
                      formatter={(v: number) => [`${v.toFixed(1)}%`, ""]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12, color: "#9ca3af" }} />
                    <Bar dataKey="actual"   fill="#22c55e" name="Actual"   radius={[3, 3, 0, 0]} />
                    <Bar dataKey="objetivo" fill="#374151" name="Objetivo" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Pie — pesos óptimos */}
              {pieData.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Pesos óptimos ({PRIMARY_STRATEGY})</p>
                  <div className="flex items-center gap-4">
                    <ResponsiveContainer width={180} height={180}>
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {pieData.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ backgroundColor: "#111827", border: "1px solid #374151", borderRadius: 8, fontSize: 12 }}
                          formatter={(v: number) => [`${v}%`, ""]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex flex-col gap-1 flex-1 min-w-0">
                      {pieData.slice(0, 10).map((d, i) => (
                        <div key={d.name} className="flex items-center gap-1.5 text-xs">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                          <span className="text-gray-400 font-mono w-10 shrink-0">{d.name}</span>
                          <span className="text-gray-200">{d.value}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Strategies comparison + Risk individual */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-2 border-t border-gray-800">
            {/* Strategies */}
            {strategiesData.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Comparación de estrategias</p>
                <div className="space-y-2">
                  {strategiesData.map((s) => (
                    <div
                      key={s.name}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs ${
                        s.isPrimary ? "bg-green-900/20 border border-green-800/40" : "bg-gray-800/40"
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className={`font-medium truncate ${s.isPrimary ? "text-green-400" : "text-gray-300"}`}>
                          {s.isPrimary && "★ "}{s.name}
                        </p>
                      </div>
                      <div className="flex gap-4 shrink-0 font-mono text-gray-400">
                        <span title="Retorno esperado">R: <span className="text-green-400">{s.ret.toFixed(1)}%</span></span>
                        <span title="Volatilidad">σ: <span className="text-yellow-400">{s.vol.toFixed(1)}%</span></span>
                        <span title="Sharpe">Sh: <span className="text-blue-400">{s.sharpe.toFixed(2)}</span></span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Risk individual */}
            {riskIndividual.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Riesgo individual (Sharpe)</p>
                <div className="space-y-1.5">
                  {riskIndividual
                    .sort((a, b) => Number(b["Sharpe"] ?? 0) - Number(a["Sharpe"] ?? 0))
                    .map((r, i) => {
                      const sharpe = Number(r["Sharpe"] ?? 0);
                      const pct = Math.min(Math.abs(sharpe) / 2 * 100, 100);
                      return (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className="font-mono text-gray-400 w-10 shrink-0">{String(r["Símbolo"] ?? "—")}</span>
                          <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${sharpe >= 0 ? "bg-green-500" : "bg-red-500"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className={`font-mono w-10 text-right ${sharpe >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {sharpe.toFixed(2)}
                          </span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ÓRDENES + SEMÁFORO ────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <p className="text-sm font-medium text-gray-300">Órdenes de rebalanceo</p>
        </div>
        {orders.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                <th className="px-4 py-3 text-left">Ticker</th>
                <th className="px-4 py-3 text-left">Acción</th>
                <th className="px-4 py-3 text-right">Monto</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => {
                const accion = String(o["Acción"] ?? "—");
                const delta  = Number(o["Δ Dólares ($)"] ?? 0);
                return (
                  <tr key={i} className="border-b border-gray-800/50">
                    <td className="px-4 py-3 font-mono font-medium text-gray-100">{String(o["Símbolo"] ?? "—")}</td>
                    <td className={`px-4 py-3 text-xs font-medium ${accion.includes("COMPR") ? "text-green-400" : accion.includes("VEND") ? "text-red-400" : "text-gray-500"}`}>
                      {accion}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono text-sm ${delta >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {delta >= 0 ? "+" : ""}{fmt(delta)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="px-5 py-8 text-sm text-gray-600 text-center">
            Sin órdenes — ejecutá Markowitz desde Pipeline.
          </p>
        )}
      </div>

      {/* ── SEMÁFORO ── */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-300">Semáforo de mercado</p>
          <button
            onClick={handleRefreshSemaforo}
            disabled={refreshing || !snapshot?.markowitz_raw}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title={snapshot?.markowitz_raw ? "Volver a correr el semáforo" : "Ejecutar Markowitz primero"}
          >
            {refreshing ? (
              <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : "🔄"} Actualizar
          </button>
        </div>

        {semCode && semInfo ? (
          <>
            {/* Decision + score */}
            <div className="flex items-start gap-4">
              <div className={`flex-1 flex items-center gap-3 p-3 rounded-lg border ${SEMAPHORE_COLORS[semCode] ?? ""}`}>
                <span className="text-2xl">
                  {{ GO: "🟢", PARTIAL: "🟡", WAIT: "🟠", ABORT: "🔴" }[semCode] ?? "⚪"}
                </span>
                <div>
                  <p className="text-sm font-semibold">{String(semInfo.decision ?? semCode)}</p>
                  <p className="text-xs text-gray-400">{String(semInfo.consejo ?? "")}</p>
                  {latestRun && (
                    <p className="text-xs text-gray-600 mt-0.5">
                      Corrido el {new Date(latestRun.ran_at).toLocaleString("es-AR")}
                    </p>
                  )}
                </div>
              </div>
              {semPuntos != null && (
                <div className="text-center shrink-0 bg-gray-800 rounded-xl px-4 py-3 min-w-[72px]">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Score</p>
                  <p className={`text-2xl font-bold font-mono ${
                    semPuntos <= 2 ? "text-green-400" : semPuntos <= 6 ? "text-yellow-400" : semPuntos <= 10 ? "text-orange-400" : "text-red-400"
                  }`}>{semPuntos}</p>
                  <p className="text-[10px] text-gray-600 mt-0.5">
                    {semPuntos <= 2 ? "GO" : semPuntos <= 6 ? "PARTIAL" : semPuntos <= 10 ? "WAIT" : "ABORT"}
                  </p>
                </div>
              )}
            </div>

            {/* VIX */}
            {semVix && (
              <div className="flex items-center gap-4 px-3 py-2 bg-gray-800/50 rounded-lg text-xs">
                <span className="text-gray-500 uppercase tracking-wider">VIX</span>
                <span className="text-gray-200 font-mono font-bold text-base">{Number(semVix.valor ?? 0).toFixed(2)}</span>
                {semVix.vs_sma20 != null && (
                  <span className={`font-mono ${Number(semVix.vs_sma20) > 0 ? "text-red-400" : "text-green-500"}`}>
                    vs SMA20: {Number(semVix.vs_sma20) >= 0 ? "+" : ""}{Number(semVix.vs_sma20).toFixed(0)}%
                  </span>
                )}
                <span className="text-gray-500">{String(semVix.nivel ?? "")}</span>
              </div>
            )}

            {/* Mercado broad */}
            {mercado && Object.keys(mercado).length > 0 && (
              <div>
                <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Mercado</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(mercado).map(([ticker, data]) => {
                    const r1 = Number(data.ret_1d ?? 0);
                    const r5 = Number(data.ret_5d ?? 0);
                    const rsi = Number(data.rsi14 ?? 50);
                    const belowSma = Boolean(data.bajo_sma50);
                    return (
                      <div key={ticker} className={`flex flex-col px-3 py-2 rounded-lg border text-xs font-mono min-w-[90px] ${
                        r1 >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"
                      }`}>
                        <span className="text-gray-300 font-semibold text-[11px] mb-0.5">{ticker}</span>
                        <span className={r1 >= 0 ? "text-green-400" : "text-red-400"}>{r1 >= 0 ? "+" : ""}{r1.toFixed(2)}%</span>
                        <span className="text-gray-500 text-[10px]">5D: {r5 >= 0 ? "+" : ""}{r5.toFixed(2)}%</span>
                        <span className="text-gray-500 text-[10px]">RSI {rsi.toFixed(0)} · {belowSma ? "⚠ SMA50" : "✓ SMA50"}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Indicadores secundarios */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Crédito */}
              {semCredito && (
                <div className="bg-gray-800/50 rounded-lg p-3 space-y-1">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Crédito (HYG)</p>
                  <p className={`text-sm font-mono font-bold ${Number(semCredito.hyg_ret_1d ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(semCredito.hyg_ret_1d ?? 0) >= 0 ? "+" : ""}{Number(semCredito.hyg_ret_1d ?? 0).toFixed(2)}%
                  </p>
                  <p className="text-[10px] text-gray-500">5D: {Number(semCredito.hyg_ret_5d ?? 0) >= 0 ? "+" : ""}{Number(semCredito.hyg_ret_5d ?? 0).toFixed(2)}%</p>
                  {Boolean(semCredito.stress) && <p className="text-[10px] text-orange-400">⚠ Stress crediticio</p>}
                </div>
              )}

              {/* Sectores */}
              {semSectores && (
                <div className="bg-gray-800/50 rounded-lg p-3 space-y-1">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Sectores</p>
                  {(["XLF", "XLU", "XLK"] as const).map((t) => {
                    const d = semSectores[t] as Record<string, unknown> | undefined;
                    if (!d) return null;
                    const r = Number(d.ret_1d ?? 0);
                    return (
                      <p key={t} className="text-[10px] font-mono">
                        <span className="text-gray-500 w-8 inline-block">{t}</span>
                        <span className={r >= 0 ? "text-green-400" : "text-red-400"}>{r >= 0 ? "+" : ""}{r.toFixed(2)}%</span>
                      </p>
                    );
                  })}
                  {Boolean(semSectores.rotacion_defensiva) && <p className="text-[10px] text-orange-400">⚠ Rotación defensiva</p>}
                  {Boolean(semSectores.stress_financiero) && <p className="text-[10px] text-red-400">⚠ Financiero bajo presión</p>}
                </div>
              )}

              {/* Tasas */}
              {semTasas && (
                <div className="bg-gray-800/50 rounded-lg p-3 space-y-1">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Tasa 10Y (TNX)</p>
                  <p className="text-sm font-mono font-bold text-gray-200">{Number(semTasas.valor ?? 0).toFixed(3)}%</p>
                  <p className="text-[10px] text-gray-500">Δ5D: {(Number(semTasas.cambio_5d ?? 0)*100).toFixed(0)} bps</p>
                  {Boolean(semTasas.spike) && <p className="text-[10px] text-orange-400">⚠ Spike de tasas</p>}
                </div>
              )}

              {/* Emergentes */}
              {semEmergentes && (
                <div className="bg-gray-800/50 rounded-lg p-3 space-y-1">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Emergentes (EEM)</p>
                  <p className={`text-sm font-mono font-bold ${Number(semEmergentes.ret_1d ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(semEmergentes.ret_1d ?? 0) >= 0 ? "+" : ""}{Number(semEmergentes.ret_1d ?? 0).toFixed(2)}%
                  </p>
                  <p className="text-[10px] text-gray-500">5D: {Number(semEmergentes.ret_5d ?? 0) >= 0 ? "+" : ""}{Number(semEmergentes.ret_5d ?? 0).toFixed(2)}%</p>
                  {Boolean(semEmergentes.stress) && <p className="text-[10px] text-orange-400">⚠ Stress en emergentes</p>}
                </div>
              )}
            </div>

            {/* Factores de riesgo */}
            {semRazones && semRazones.length > 0 && (
              <div className="border-t border-gray-800 pt-3">
                <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Factores de riesgo</p>
                <ul className="space-y-0.5">
                  {semRazones.map((r, i) => (
                    <li key={i} className="text-xs text-gray-400 flex items-start gap-1.5">
                      <span className="text-orange-500 mt-0.5 shrink-0">•</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : (
          <p className="text-sm text-gray-600 py-4 text-center">
            Sin datos — ejecutá el Semáforo desde Pipeline.
          </p>
        )}
      </div>
      </div>{/* end grid */}

      {/* Holdings table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <p className="text-sm font-medium text-gray-300">Holdings</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
              <th className="px-5 py-3 text-left">Ticker</th>
              <th className="px-5 py-3 text-right">Qty</th>
              <th className="px-5 py-3 text-right">Precio</th>
              <th className="px-5 py-3 text-right">Valor</th>
              <th className="px-5 py-3 text-right">Peso</th>
              <th className="px-5 py-3 text-right">P&L</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.holdings
              .sort((a, b) => Number(b.market_value) - Number(a.market_value))
              .map((h) => (
                <tr key={h.symbol} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono font-medium text-gray-100">{h.symbol}</td>
                  <td className="px-5 py-3 text-right text-gray-400 font-mono">{Number(h.qty).toFixed(4)}</td>
                  <td className="px-5 py-3 text-right text-gray-300">{fmt(h.market_price)}</td>
                  <td className="px-5 py-3 text-right text-gray-300">{fmt(h.market_value)}</td>
                  <td className="px-5 py-3 text-right text-gray-300">{Number(h.weight).toFixed(1)}%</td>
                  <td className={`px-5 py-3 text-right font-mono ${Number(h.pnl_pct) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(h.pnl_pct) >= 0 ? "+" : ""}{Number(h.pnl_pct).toFixed(2)}%
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Dividends */}
      {snapshot.dividends.length > 0 && (() => {
        const gross = snapshot.dividends.filter(d => Number(d.amount) > 0);
        const withholding = snapshot.dividends.filter(d => Number(d.amount) < 0);
        const totalGross = gross.reduce((s, d) => s + Number(d.amount), 0);
        const totalNet   = snapshot.dividends.reduce((s, d) => s + Number(d.amount), 0);
        return (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <p className="text-sm font-medium text-gray-300">Dividendos del período</p>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-gray-500">Bruto: <span className="text-green-400 font-mono">{fmt(totalGross)}</span></span>
                <span className="text-gray-500">Retención: <span className="text-red-400 font-mono">{fmt(totalNet - totalGross)}</span></span>
                <span className="text-gray-500">Neto: <span className="text-white font-mono font-semibold">{fmt(totalNet)}</span></span>
              </div>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                  <th className="px-5 py-3 text-left">Fecha</th>
                  <th className="px-5 py-3 text-left">Ticker</th>
                  <th className="px-5 py-3 text-left">Tipo</th>
                  <th className="px-5 py-3 text-right">Monto</th>
                </tr>
              </thead>
              <tbody>
                {[...gross, ...withholding]
                  .sort((a, b) => a.symbol.localeCompare(b.symbol) || a.date.localeCompare(b.date))
                  .map((d, i) => (
                    <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/20">
                      <td className="px-5 py-2.5 text-gray-500 font-mono text-xs">{d.date}</td>
                      <td className="px-5 py-2.5 font-mono font-medium text-gray-100">{d.symbol || "—"}</td>
                      <td className="px-5 py-2.5 text-gray-500 text-xs">{d.event_type}</td>
                      <td className={`px-5 py-2.5 text-right font-mono ${Number(d.amount) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {Number(d.amount) >= 0 ? "+" : ""}{fmt(Number(d.amount))}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        );
      })()}

      {/* Transactions */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
          <p className="text-sm font-medium text-gray-300">Transacciones del período</p>
          {snapshot.transactions.length > 0 && (
            <span className="text-xs text-gray-500">{snapshot.transactions.length} operaciones</span>
          )}
        </div>
        {snapshot.transactions.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                <th className="px-5 py-3 text-left">Fecha</th>
                <th className="px-5 py-3 text-left">Ticker</th>
                <th className="px-5 py-3 text-left">Lado</th>
                <th className="px-5 py-3 text-right">Qty</th>
                <th className="px-5 py-3 text-right">Precio</th>
                <th className="px-5 py-3 text-right">Monto</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.transactions
                .sort((a, b) => b.date.localeCompare(a.date))
                .map((t, i) => {
                  const isBuy = t.side.toUpperCase().includes("BUY") || t.side.toUpperCase().includes("COMPR");
                  return (
                    <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/20">
                      <td className="px-5 py-2.5 text-gray-500 font-mono text-xs">{t.date}</td>
                      <td className="px-5 py-2.5 font-mono font-medium text-gray-100">{t.symbol || "—"}</td>
                      <td className="px-5 py-2.5">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${isBuy ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                          {t.side || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-right text-gray-400 font-mono">{Number(t.qty).toFixed(4)}</td>
                      <td className="px-5 py-2.5 text-right text-gray-300 font-mono">{fmt(t.price)}</td>
                      <td className={`px-5 py-2.5 text-right font-mono ${Number(t.amount) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {Number(t.amount) >= 0 ? "+" : ""}{fmt(Math.abs(Number(t.amount)))}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        ) : (
          <p className="px-5 py-8 text-sm text-gray-600 text-center">Sin transacciones registradas en este período.</p>
        )}
      </div>

      {/* Advisor report */}
      {snapshot.advisor_report && (
        <AdvisorReport
          report={snapshot.advisor_report}
          downloadName={`reporte_asesor_${snapshot.period.replace(/ /g, "_")}.md`}
        />
      )}
    </div>
  );
}
