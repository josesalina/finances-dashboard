import { useState, useRef, useEffect } from "react";
import api from "../api/client";

interface Signal { metric: string; value: string; signal: string; }
interface Level  { precio: number; confirmaciones: number; origen: string; dist_pct: number; }

interface StockData {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  is_etf: boolean;
  price: {
    current: number;
    week52_high: number;
    week52_low: number;
    range_pct?: number;
    pct_from_high?: number;
    pct_from_low?: number;
  };
  fundamentals: {
    score: number;
    max_score: number;
    score_pct: number;
    verdict: string;
    verdict_emoji: string;
    signals: Signal[];
  };
  technical: {
    rsi: number;
    rsi_signal: string;
    macd: number;
    macd_signal: string;
  };
  supports: Level[];
  resistances: Level[];
  summary: {
    recommendation: string;
    recommendation_label: string;
    target_mean: number | null;
    target_upside_pct: number | null;
    key_support: Level | null;
    key_resistance: Level | null;
  };
  dividend_yield: number | null;
}

function fmt(n: number | null | undefined, prefix = "$") {
  if (n == null) return "—";
  return `${prefix}${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function pct(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

const VERDICT_STYLES: Record<string, string> = {
  "OPORTUNIDAD": "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/30",
  "PRECIO JUSTO": "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/30",
  "ALGO CARA":   "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30",
  "CARA":        "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30",
};
const REC_STYLES: Record<string, string> = {
  "COMPRA FUERTE": "text-green-600 dark:text-green-400",
  "COMPRA":        "text-green-600 dark:text-green-400",
  "MANTENER":      "text-yellow-600 dark:text-yellow-400",
  "VENDER":        "text-red-600 dark:text-red-400",
  "VENTA FUERTE":  "text-red-600 dark:text-red-400",
};

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "SPY", "XOM", "KO", "GOOG", "BMA"];

export default function StockSearch() {
  const [query, setQuery]     = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData]       = useState<StockData | null>(null);
  const [error, setError]     = useState<string | null>(null);
  const [quickPicks, setQuickPicks] = useState<string[]>(DEFAULT_TICKERS);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get("/snapshots/current/").then((r) => {
      const holdings: { symbol: string; weight: number }[] = r.data.holdings ?? [];
      if (holdings.length > 0) {
        const sorted = [...holdings]
          .sort((a, b) => Number(b.weight) - Number(a.weight))
          .map((h) => h.symbol);
        setQuickPicks(sorted);
      }
    }).catch(() => {});
  }, []);

  const search = async (ticker = query) => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const { data: result } = await api.get<StockData>(`/analyze/${t}/`);
      setData(result);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? (err instanceof Error ? err.message : String(err));
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const rangeColor = (p?: number) => {
    if (p == null) return "text-gray-500";
    if (p < 30) return "text-green-600 dark:text-green-400";
    if (p > 70) return "text-red-600 dark:text-red-400";
    return "text-yellow-600 dark:text-yellow-400";
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Buscador de Acciones</h2>
        <p className="text-sm text-gray-500 mt-0.5">Análisis fundamental y técnico por ticker.</p>
      </div>

      {/* Search bar */}
      <form
        onSubmit={(e) => { e.preventDefault(); search(); }}
        className="flex gap-3"
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          placeholder="AAPL, SPY, XOM…"
          className="flex-1 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 font-mono text-sm focus:outline-none focus:border-green-600 transition-colors"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-6 py-3 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Analizando…" : "Analizar"}
        </button>
      </form>

      {/* Quick picks */}
      <div className="flex flex-wrap gap-2">
        {quickPicks.map((t) => (
          <button
            key={t}
            onClick={() => { setQuery(t); search(t); }}
            className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-white transition-colors font-mono"
          >
            {t}
          </button>
        ))}
      </div>

      {error && (
        <div className="border border-red-500/30 bg-red-500/10 rounded-xl px-5 py-4 text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-16 text-gray-500 text-sm">
          Consultando yfinance…
        </div>
      )}

      {data && !loading && (
        <div className="space-y-5">
          {/* Header */}
          <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-6 py-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold font-mono text-gray-900 dark:text-white">{data.ticker}</span>
                  {data.is_etf && <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-600 dark:text-blue-400 border border-blue-500/30 rounded-full">ETF</span>}
                </div>
                <p className="text-gray-500 dark:text-gray-400 mt-0.5">{data.name}</p>
                {data.sector && <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">{data.sector} › {data.industry}</p>}
              </div>
              <div className="text-right">
                <p className="text-3xl font-bold text-gray-900 dark:text-white">{fmt(data.price.current)}</p>
                {data.dividend_yield != null && (
                  <p className="text-xs text-gray-500 mt-1">💰 Dividendo: {data.dividend_yield.toFixed(2)}%</p>
                )}
              </div>
            </div>

            {/* 52w range bar */}
            {data.price.range_pct != null && (
              <div className="mt-5">
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Mín 52s: {fmt(data.price.week52_low)}</span>
                  <span className={`font-medium ${rangeColor(data.price.range_pct)}`}>
                    {data.price.range_pct.toFixed(0)}% del rango
                  </span>
                  <span>Máx 52s: {fmt(data.price.week52_high)}</span>
                </div>
                <div className="h-1.5 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${data.price.range_pct < 30 ? "bg-green-500" : data.price.range_pct > 70 ? "bg-red-500" : "bg-yellow-500"}`}
                    style={{ width: `${data.price.range_pct}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-gray-400 dark:text-gray-600 mt-1">
                  <span>{pct(data.price.pct_from_low)} desde mín</span>
                  <span>{pct(data.price.pct_from_high)} desde máx</span>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Fundamentals */}
            <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Análisis Fundamental</p>
                <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${VERDICT_STYLES[data.fundamentals.verdict] ?? ""}`}>
                  {data.fundamentals.verdict_emoji} {data.fundamentals.verdict}
                </span>
              </div>

              {/* Score bar */}
              <div className="px-5 py-3 border-b border-gray-200/50 dark:border-gray-800/50">
                <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
                  <span>Score</span>
                  <span className="font-mono">{data.fundamentals.score} / {data.fundamentals.max_score}</span>
                </div>
                <div className="h-1.5 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full"
                    style={{ width: `${Math.max(0, ((data.fundamentals.score + data.fundamentals.max_score) / (data.fundamentals.max_score * 2)) * 100)}%` }}
                  />
                </div>
              </div>

              <div className="divide-y divide-gray-200/50 dark:divide-gray-800/50">
                {data.fundamentals.signals.map((s, i) => (
                  <div key={i} className="flex items-center justify-between px-5 py-2.5 text-sm">
                    <span className="text-gray-500 text-xs w-36 shrink-0">{s.metric}</span>
                    <span className="text-gray-700 dark:text-gray-300 font-mono text-xs flex-1 text-center">{s.value}</span>
                    <span className="text-xs text-right shrink-0">{s.signal}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Technical + Summary */}
            <div className="space-y-5">
              {/* Technical indicators */}
              {data.technical.rsi != null && (
                <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-4">
                  <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Técnico</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-100 dark:bg-gray-950 rounded-lg px-4 py-3">
                      <p className="text-xs text-gray-500 mb-1">RSI (14)</p>
                      <p className={`text-xl font-bold font-mono ${data.technical.rsi < 30 ? "text-green-600 dark:text-green-400" : data.technical.rsi > 70 ? "text-red-600 dark:text-red-400" : "text-yellow-600 dark:text-yellow-400"}`}>
                        {data.technical.rsi}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-600 mt-0.5">
                        {data.technical.rsi_signal === "oversold" ? "Sobrevendido 🟢" : data.technical.rsi_signal === "overbought" ? "Sobrecomprado 🔴" : "Neutral 🟡"}
                      </p>
                    </div>
                    <div className="bg-gray-100 dark:bg-gray-950 rounded-lg px-4 py-3">
                      <p className="text-xs text-gray-500 mb-1">MACD</p>
                      <p className={`text-xl font-bold font-mono ${data.technical.macd > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                        {data.technical.macd > 0 ? "+" : ""}{data.technical.macd}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-600 mt-0.5">
                        {data.technical.macd_signal === "bullish" ? "Alcista 🟢" : "Bajista 🔴"}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Resumen</p>
                {data.summary.recommendation_label && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Consenso analistas</span>
                    <span className={`font-semibold ${REC_STYLES[data.summary.recommendation_label] ?? "text-gray-600 dark:text-gray-300"}`}>
                      {data.summary.recommendation_label}
                    </span>
                  </div>
                )}
                {data.summary.target_mean != null && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Target promedio</span>
                    <span className="text-gray-700 dark:text-gray-200 font-mono">
                      {fmt(data.summary.target_mean)}
                      {data.summary.target_upside_pct != null && (
                        <span className={`ml-1.5 text-xs ${data.summary.target_upside_pct >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                          ({pct(data.summary.target_upside_pct)})
                        </span>
                      )}
                    </span>
                  </div>
                )}
                {data.summary.key_support && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Soporte clave</span>
                    <span className="text-green-600 dark:text-green-400 font-mono">
                      {fmt(data.summary.key_support.precio)}
                      <span className="text-xs text-gray-500 ml-1.5">({pct(data.summary.key_support.dist_pct)})</span>
                    </span>
                  </div>
                )}
                {data.summary.key_resistance && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Resistencia clave</span>
                    <span className="text-red-600 dark:text-red-400 font-mono">
                      {fmt(data.summary.key_resistance.precio)}
                      <span className="text-xs text-gray-500 ml-1.5">({pct(data.summary.key_resistance.dist_pct)})</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Support & Resistance table */}
          {(data.supports.length > 0 || data.resistances.length > 0) && (
            <div className="grid grid-cols-2 gap-5">
              {[
                { label: "🟢 Soportes",    items: data.supports,    color: "text-green-600 dark:text-green-400" },
                { label: "🔴 Resistencias", items: data.resistances, color: "text-red-600 dark:text-red-400" },
              ].map(({ label, items, color }) => (
                <div key={label} className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
                  <div className="px-5 py-3 border-b border-gray-200 dark:border-gray-800">
                    <p className="text-sm font-medium text-gray-600 dark:text-gray-300">{label}</p>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-gray-400 dark:text-gray-600 uppercase border-b border-gray-200 dark:border-gray-800">
                        <th className="px-4 py-2 text-left">Precio</th>
                        <th className="px-4 py-2 text-center">Dist.</th>
                        <th className="px-4 py-2 text-center">Conf.</th>
                        <th className="px-4 py-2 text-left">Origen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((lvl, i) => (
                        <tr key={i} className="border-b border-gray-200/40 dark:border-gray-800/40 hover:bg-gray-100/30 dark:hover:bg-gray-800/30">
                          <td className={`px-4 py-2.5 font-mono font-medium ${color}`}>{fmt(lvl.precio)}</td>
                          <td className="px-4 py-2.5 text-center text-gray-500 font-mono text-xs">{pct(lvl.dist_pct)}</td>
                          <td className="px-4 py-2.5 text-center">{"⭐".repeat(Math.min(lvl.confirmaciones, 4))}</td>
                          <td className="px-4 py-2.5 text-gray-500 text-xs">{lvl.origen}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}

          <p className="text-xs text-gray-400 dark:text-gray-700 text-center pb-2">
            ⚠️ Análisis informativo — no constituye asesoramiento financiero.
          </p>
        </div>
      )}
    </div>
  );
}
