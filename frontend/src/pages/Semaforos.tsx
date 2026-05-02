import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";
import type { SemaphoreRun, SnapshotSummary } from "../api/types";

const SEMAPHORE_COLORS: Record<string, string> = {
  GO:      "bg-green-500/20 text-green-400 border-green-500/30",
  PARTIAL: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  WAIT:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  ABORT:   "bg-red-500/20 text-red-400 border-red-500/30",
};

const SEMAPHORE_EMOJI: Record<string, string> = {
  GO: "🟢", PARTIAL: "🟡", WAIT: "🟠", ABORT: "🔴",
};

function formatDate(iso: string) {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export default function Semaforos() {
  const [runs, setRuns] = useState<SemaphoreRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const loadRuns = () => {
    setLoading(true);
    api.get<SemaphoreRun[]>("/semaphore-runs/")
      .then((r) => setRuns(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadRuns();
    api.get<SnapshotSummary[]>("/snapshots/").then((r) => {
      setSnapshots(r.data);
      if (r.data.length > 0) setSelectedSnapshotId(String(r.data[0].id));
    });
  }, []);

  const handleRun = async () => {
    if (!selectedSnapshotId) return;
    setRunning(true);
    setRunError(null);
    try {
      await api.post("/semaphore-runs/run/", { snapshot_id: Number(selectedSnapshotId) });
      setShowForm(false);
      loadRuns();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? "Error al correr el semáforo";
      setRunError(msg);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">Semáforos</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Historial de corridas · cada ejecución refleja las condiciones del mercado en ese momento
          </p>
        </div>
        <button
          onClick={() => { setShowForm(!showForm); setRunError(null); }}
          className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          ▶ Correr semáforo
        </button>
      </div>

      {/* Inline run form */}
      {showForm && (
        <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 space-y-4">
          <p className="text-sm font-medium text-gray-300">Seleccionar snapshot</p>
          <div className="flex items-center gap-3 flex-wrap">
            <select
              value={selectedSnapshotId}
              onChange={(e) => setSelectedSnapshotId(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            >
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>{s.period}</option>
              ))}
            </select>
            <button
              onClick={handleRun}
              disabled={running || !selectedSnapshotId}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {running ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Corriendo…
                </>
              ) : "Ejecutar"}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-gray-500 hover:text-gray-300 text-sm"
            >
              Cancelar
            </button>
          </div>
          {runError && (
            <p className="text-sm text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">{runError}</p>
          )}
          {running && (
            <p className="text-xs text-gray-500">Esto puede tardar entre 10 y 30 segundos mientras se descarga datos del mercado…</p>
          )}
        </div>
      )}

      {/* Runs table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <p className="px-5 py-8 text-sm text-gray-500 text-center">Cargando…</p>
        ) : runs.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-600 text-center">Sin corridas registradas.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                <th className="px-4 py-3 text-left">Snapshot</th>
                <th className="px-4 py-3 text-left">Ejecutado</th>
                <th className="px-4 py-3 text-left">Código</th>
                <th className="px-4 py-3 text-left">VIX</th>
                <th className="px-4 py-3 text-left">Decisión</th>
                <th className="px-4 py-3 text-left">Consejo</th>
                <th className="px-4 py-3 text-center w-10"></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const vix = run.semaforo_raw?.vix as Record<string, unknown> | undefined;
                const sem = run.semaforo_raw?.semaforo as Record<string, unknown> | undefined;
                const code = run.semaphore_code ?? "";
                const isExpanded = expandedId === run.id;

                return (
                  <>
                    <tr
                      key={run.id}
                      className="border-b border-gray-800/50 hover:bg-gray-800/20"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to={`/months/${run.snapshot_id}`}
                          className="text-blue-400 hover:text-blue-300 font-mono text-xs"
                        >
                          {run.period}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-400 font-mono text-xs whitespace-nowrap">
                        {formatDate(run.ran_at)}
                      </td>
                      <td className="px-4 py-3">
                        {code ? (
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${SEMAPHORE_COLORS[code] ?? "bg-gray-800 text-gray-400 border-gray-700"}`}>
                            {SEMAPHORE_EMOJI[code] ?? "⚪"} {code}
                          </span>
                        ) : (
                          <span className="text-gray-600 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {vix ? (
                          <div>
                            <span className="text-gray-200 font-mono text-xs">
                              {Number(vix.valor ?? 0).toFixed(2)}
                            </span>
                            <p className="text-gray-600 text-xs">{String(vix.nivel ?? "")}</p>
                          </div>
                        ) : (
                          <span className="text-gray-600 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-300 text-xs">
                        {String(sem?.decision ?? "—")}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px]">
                        <span title={String(sem?.consejo ?? "")}>
                          {truncate(String(sem?.consejo ?? ""), 60)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => setExpandedId(isExpanded ? null : run.id)}
                          className="text-gray-600 hover:text-gray-300 transition-colors"
                          title={isExpanded ? "Colapsar" : "Expandir"}
                        >
                          <svg
                            className={`w-4 h-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${run.id}-detail`} className="border-b border-gray-800/50 bg-gray-900/60">
                        <td colSpan={7} className="px-6 py-5">
                          <ExpandedDetail run={run} />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ExpandedDetail({ run }: { run: SemaphoreRun }) {
  const mercado = run.semaforo_raw?.mercado as Record<string, Record<string, unknown>> | undefined;
  const sem = run.semaforo_raw?.semaforo as Record<string, unknown> | undefined;

  return (
    <div className="space-y-4">
      {/* Consejo full */}
      {sem?.consejo != null && (
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Consejo completo</p>
          <p className="text-sm text-gray-300">{String(sem.consejo)}</p>
        </div>
      )}

      {/* Market returns */}
      {mercado && Object.keys(mercado).length > 0 && (
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Retornos del mercado (1d)</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(mercado).map(([ticker, data]) => {
              const ret = Number(data.ret_1d ?? 0);
              const isPos = ret >= 0;
              return (
                <div
                  key={ticker}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono ${
                    isPos
                      ? "bg-green-500/10 border-green-500/30 text-green-400"
                      : "bg-red-500/10 border-red-500/30 text-red-400"
                  }`}
                >
                  <span className="text-gray-300 font-semibold">{ticker}</span>
                  <span>{isPos ? "+" : ""}{ret.toFixed(2)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
