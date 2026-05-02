import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import AdvisorReport from "../components/AdvisorReport";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import api from "../api/client";
import type { SnapshotDetail } from "../api/types";

const SEMAPHORE_COLORS: Record<string, string> = {
  GO:      "bg-green-500/20 text-green-400 border-green-500/30",
  PARTIAL: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  WAIT:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  ABORT:   "bg-red-500/20 text-red-400 border-red-500/30",
};

function fmt(n: number | string) {
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function MonthReport() {
  const { id } = useParams<{ id: string }>();
  const [snapshot, setSnapshot] = useState<SnapshotDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api.get<SnapshotDetail>(`/snapshots/${id}/`)
      .then((r) => setSnapshot(r.data))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-6 text-gray-500 text-sm">Cargando…</div>;
  if (!snapshot) return <div className="p-6 text-gray-500 text-sm">Snapshot no encontrado.</div>;

  const semRaw  = snapshot.semaforo_raw as Record<string, unknown> | null;
  const semInfo = semRaw?.semaforo as Record<string, unknown> | null;
  const semCode = (semInfo?.code as string | undefined) ?? snapshot.semaphore_code;
  const mercado = semRaw?.mercado as Record<string, Record<string, unknown>> | null;

  // Weights chart data — only holdings with target_weight
  const weightsData = snapshot.holdings
    .filter((h) => h.target_weight !== null)
    .map((h) => ({
      symbol: h.symbol,
      actual: Number(h.weight),
      objetivo: Number(h.target_weight),
    }));

  // Markowitz orders  — field names use Spanish with special chars from the script
  const markowitzRaw = snapshot.markowitz_raw as Record<string, unknown> | null;
  const orders = (markowitzRaw?.orders as Array<Record<string, unknown>> | undefined) ?? [];

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

      {/* Weights chart (only if Markowitz ran) */}
      {weightsData.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <p className="text-sm font-medium text-gray-300 mb-1">Pesos: actual vs objetivo Markowitz</p>
          <p className="text-xs text-gray-600 mb-4">Estrategia conservadora — Sharpe máximo con tope 12%</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weightsData} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="symbol" tick={{ fill: "#6b7280", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: "#111827", border: "1px solid #374151", borderRadius: 8 }}
                formatter={(v: number) => [`${v}%`, ""]}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "#9ca3af" }} />
              <Bar dataKey="actual"   fill="#22c55e" name="Actual"   radius={[3, 3, 0, 0]} />
              <Bar dataKey="objetivo" fill="#374151" name="Objetivo" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Orders + Semaphore */}
      <div className="grid grid-cols-2 gap-4">
        {/* Orders */}
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

        {/* Semaphore */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
          <p className="text-sm font-medium text-gray-300">Semáforo de mercado</p>
          {semCode && semInfo ? (
            <>
              <div className={`flex items-center gap-3 p-3 rounded-lg border ${SEMAPHORE_COLORS[semCode] ?? ""}`}>
                <span className="text-2xl">
                  {{ GO: "🟢", PARTIAL: "🟡", WAIT: "🟠", ABORT: "🔴" }[semCode] ?? "⚪"}
                </span>
                <div>
                  <p className="text-sm font-semibold">{String(semInfo.decision ?? semCode)}</p>
                  <p className="text-xs text-gray-400">{String(semInfo.consejo ?? "")}</p>
                </div>
              </div>
              {mercado && Object.entries(mercado).slice(0, 5).map(([ticker, data]) => (
                <div key={ticker} className="flex items-center justify-between text-sm">
                  <span className="text-gray-500 font-mono">{ticker}</span>
                  <span className={`font-mono text-xs ${Number(data.ret_1d ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {Number(data.ret_1d ?? 0) >= 0 ? "+" : ""}{Number(data.ret_1d ?? 0).toFixed(2)}% (1d)
                  </span>
                </div>
              ))}
              {semRaw?.vix && (
                <div className="flex items-center justify-between text-sm pt-1 border-t border-gray-800">
                  <span className="text-gray-500">VIX</span>
                  <span className="text-gray-200 font-mono text-xs">
                    {Number((semRaw.vix as Record<string, unknown>).valor ?? 0).toFixed(2)}
                    {" · "}{String((semRaw.vix as Record<string, unknown>).nivel ?? "")}
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-600 py-4 text-center">
              Sin datos — ejecutá el Semáforo desde Pipeline.
            </p>
          )}
        </div>
      </div>

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
