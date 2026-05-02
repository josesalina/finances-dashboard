import { useState, useRef, useEffect } from "react";
import api from "../api/client";

interface Signal { metric: string; value: string; signal: string; }
interface Level  { precio: number; confirmaciones: number; origen: string; dist_pct: number; }
interface StockData {
  ticker: string; name: string; sector: string; industry: string; is_etf: boolean;
  price: { current: number; week52_high: number; week52_low: number; range_pct?: number; pct_from_high?: number; pct_from_low?: number; };
  fundamentals: { score: number; max_score: number; verdict: string; verdict_emoji: string; signals: Signal[]; };
  technical: { rsi: number; rsi_signal: string; macd: number; macd_signal: string; };
  supports: Level[]; resistances: Level[];
  summary: { recommendation_label: string; target_mean: number | null; target_upside_pct: number | null; key_support: Level | null; key_resistance: Level | null; };
  dividend_yield: number | null;
}

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function pct(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

const VERDICT_STYLES: Record<string, string> = {
  "OPORTUNIDAD": "bg-green-500/10 text-green-400 border-green-500/30",
  "PRECIO JUSTO": "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  "ALGO CARA":   "bg-orange-500/10 text-orange-400 border-orange-500/30",
  "CARA":        "bg-red-500/10 text-red-400 border-red-500/30",
};
const REC_STYLES: Record<string, string> = {
  "COMPRA FUERTE": "text-green-400", "COMPRA": "text-green-400",
  "MANTENER": "text-yellow-400", "VENDER": "text-red-400", "VENTA FUERTE": "text-red-400",
};

interface Props { onClose: () => void; tickers?: string[]; }

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "SPY", "XOM", "KO", "GOOG", "BMA", "SCHD"];

export default function StockSearchPanel({ onClose, tickers }: Props) {
  const quickPicks = tickers && tickers.length > 0 ? tickers : DEFAULT_TICKERS;
  const [query, setQuery]     = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData]       = useState<StockData | null>(null);
  const [error, setError]     = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const search = async (ticker = query) => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setLoading(true); setError(null); setData(null);
    try {
      const { data: result } = await api.get<StockData>(`/analyze/?ticker=${t}`);
      setData(result);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? (err instanceof Error ? err.message : String(err));
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed top-0 right-0 h-full w-full max-w-2xl bg-gray-950 border-l border-gray-800 z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800 shrink-0">
          <form onSubmit={(e) => { e.preventDefault(); search(); }} className="flex-1 flex gap-2">
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase())}
              placeholder="Ticker — AAPL, SPY, XOM…"
              className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-600 font-mono text-sm focus:outline-none focus:border-green-600 transition-colors"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "…" : "Analizar"}
            </button>
          </form>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-lg leading-none">✕</button>
        </div>

        {/* Quick picks */}
        <div className="flex gap-2 px-5 py-3 border-b border-gray-800/50 shrink-0 flex-wrap">
          {quickPicks.map((t) => (
            <button key={t} onClick={() => { setQuery(t); search(t); }}
              className="px-2.5 py-1 text-xs bg-gray-800 text-gray-400 rounded-md hover:bg-gray-700 hover:text-white transition-colors font-mono">
              {t}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="m-5 border border-red-500/30 bg-red-500/10 rounded-xl px-5 py-4 text-sm text-red-400">❌ {error}</div>
          )}
          {loading && (
            <div className="text-center py-20 text-gray-500 text-sm">Consultando yfinance…</div>
          )}
          {!data && !loading && !error && (
            <div className="text-center py-20 text-gray-600 text-sm">Ingresá un ticker para analizar.</div>
          )}

          {data && !loading && (
            <div className="p-5 space-y-4">
              {/* Header */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl font-bold font-mono text-white">{data.ticker}</span>
                      {data.is_etf && <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-full">ETF</span>}
                    </div>
                    <p className="text-gray-400 text-sm mt-0.5">{data.name}</p>
                    {data.sector && <p className="text-xs text-gray-600 mt-0.5">{data.sector} › {data.industry}</p>}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-2xl font-bold text-white">{fmt(data.price.current)}</p>
                    {data.dividend_yield != null && <p className="text-xs text-gray-500 mt-0.5">💰 {data.dividend_yield.toFixed(2)}% div.</p>}
                  </div>
                </div>

                {data.price.range_pct != null && (
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>{fmt(data.price.week52_low)}</span>
                      <span className={data.price.range_pct < 30 ? "text-green-400" : data.price.range_pct > 70 ? "text-red-400" : "text-yellow-400"}>
                        {data.price.range_pct.toFixed(0)}% del rango 52s
                      </span>
                      <span>{fmt(data.price.week52_high)}</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${data.price.range_pct < 30 ? "bg-green-500" : data.price.range_pct > 70 ? "bg-red-500" : "bg-yellow-500"}`}
                        style={{ width: `${data.price.range_pct}%` }} />
                    </div>
                    <div className="flex justify-between text-xs text-gray-600 mt-1">
                      <span>{pct(data.price.pct_from_low)} desde mín</span>
                      <span>{pct(data.price.pct_from_high)} desde máx</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Fundamentals */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
                  <p className="text-sm font-medium text-gray-300">Fundamentos</p>
                  <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${VERDICT_STYLES[data.fundamentals.verdict] ?? ""}`}>
                    {data.fundamentals.verdict_emoji} {data.fundamentals.verdict}
                  </span>
                </div>
                <div className="px-5 py-2 border-b border-gray-800/50">
                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-green-500 rounded-full"
                      style={{ width: `${Math.max(0, ((data.fundamentals.score + data.fundamentals.max_score) / (data.fundamentals.max_score * 2)) * 100)}%` }} />
                  </div>
                  <p className="text-xs text-gray-600 mt-1">Score: {data.fundamentals.score} / {data.fundamentals.max_score}</p>
                </div>
                <div className="divide-y divide-gray-800/50">
                  {data.fundamentals.signals.map((s, i) => (
                    <div key={i} className="flex items-center px-5 py-2 text-xs gap-2">
                      <span className="text-gray-500 w-32 shrink-0">{s.metric}</span>
                      <span className="text-gray-300 font-mono flex-1">{s.value}</span>
                      <span className="text-right shrink-0">{s.signal}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Technical + Summary */}
              <div className="grid grid-cols-2 gap-4">
                {data.technical.rsi != null && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                    <p className="text-sm font-medium text-gray-300">Técnico</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-gray-950 rounded-lg px-3 py-2">
                        <p className="text-xs text-gray-500">RSI (14)</p>
                        <p className={`text-lg font-bold font-mono mt-0.5 ${data.technical.rsi < 30 ? "text-green-400" : data.technical.rsi > 70 ? "text-red-400" : "text-yellow-400"}`}>
                          {data.technical.rsi}
                        </p>
                        <p className="text-xs text-gray-600">
                          {data.technical.rsi_signal === "oversold" ? "Sobrevendido" : data.technical.rsi_signal === "overbought" ? "Sobrecomprado" : "Neutral"}
                        </p>
                      </div>
                      <div className="bg-gray-950 rounded-lg px-3 py-2">
                        <p className="text-xs text-gray-500">MACD</p>
                        <p className={`text-lg font-bold font-mono mt-0.5 ${data.technical.macd > 0 ? "text-green-400" : "text-red-400"}`}>
                          {data.technical.macd > 0 ? "+" : ""}{data.technical.macd}
                        </p>
                        <p className="text-xs text-gray-600">{data.technical.macd_signal === "bullish" ? "Alcista" : "Bajista"}</p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
                  <p className="text-sm font-medium text-gray-300">Resumen</p>
                  {data.summary.recommendation_label && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Analistas</span>
                      <span className={`font-semibold ${REC_STYLES[data.summary.recommendation_label] ?? "text-gray-300"}`}>{data.summary.recommendation_label}</span>
                    </div>
                  )}
                  {data.summary.target_mean != null && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Target</span>
                      <span className="text-gray-200 font-mono">
                        {fmt(data.summary.target_mean)}
                        {data.summary.target_upside_pct != null && (
                          <span className={`ml-1 ${data.summary.target_upside_pct >= 0 ? "text-green-400" : "text-red-400"}`}>({pct(data.summary.target_upside_pct)})</span>
                        )}
                      </span>
                    </div>
                  )}
                  {data.summary.key_support && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Soporte</span>
                      <span className="text-green-400 font-mono">{fmt(data.summary.key_support.precio)} <span className="text-gray-500">({pct(data.summary.key_support.dist_pct)})</span></span>
                    </div>
                  )}
                  {data.summary.key_resistance && (
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">Resistencia</span>
                      <span className="text-red-400 font-mono">{fmt(data.summary.key_resistance.precio)} <span className="text-gray-500">({pct(data.summary.key_resistance.dist_pct)})</span></span>
                    </div>
                  )}
                </div>
              </div>

              {/* Support & Resistance */}
              {(data.supports.length > 0 || data.resistances.length > 0) && (
                <div className="grid grid-cols-2 gap-4">
                  {[
                    { label: "🟢 Soportes", items: data.supports, color: "text-green-400" },
                    { label: "🔴 Resistencias", items: data.resistances, color: "text-red-400" },
                  ].map(({ label, items, color }) => (
                    <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                      <p className="px-4 py-2.5 text-xs font-medium text-gray-400 border-b border-gray-800">{label}</p>
                      <table className="w-full text-xs">
                        <tbody>
                          {items.map((lvl, i) => (
                            <tr key={i} className="border-b border-gray-800/40">
                              <td className={`px-3 py-2 font-mono font-medium ${color}`}>{fmt(lvl.precio)}</td>
                              <td className="px-3 py-2 text-gray-500 font-mono">{pct(lvl.dist_pct)}</td>
                              <td className="px-3 py-2">{"⭐".repeat(Math.min(lvl.confirmaciones, 4))}</td>
                              <td className="px-3 py-2 text-gray-600 truncate max-w-24">{lvl.origen}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              )}

              <p className="text-xs text-gray-700 text-center pb-1">
                ⚠️ Análisis informativo — no constituye asesoramiento financiero.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
