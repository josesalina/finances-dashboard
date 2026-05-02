import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import AdvisorReport from "../components/AdvisorReport";

type ScriptStatus = "idle" | "running" | "done" | "error";

interface Script {
  key: string;
  label: string;
  description: string;
  depends?: string;
}

const SCRIPTS: Script[] = [
  {
    key: "parse_pdf",
    label: "1. Parse Alpaca PDF",
    description: "Extrae holdings, transacciones y dividendos del estado de cuenta.",
  },
  {
    key: "markowitz",
    label: "2. Rebalanceo Markowitz",
    description: "Calcula el portafolio óptimo por máximo Sharpe Ratio.",
    depends: "parse_pdf",
  },
  {
    key: "semaforo",
    label: "3. Semáforo de Mercado",
    description: "Evalúa VIX y SPY para determinar si es buen momento para operar.",
    depends: "markowitz",
  },
  {
    key: "asesor",
    label: "4. Asesor Financiero",
    description: "Genera el reporte consolidado del mes.",
    depends: "semaforo",
  },
];

const STATUS_STYLES: Record<ScriptStatus, string> = {
  idle:    "border-gray-700 bg-gray-900",
  running: "border-blue-500/50 bg-blue-950/20",
  done:    "border-green-500/50 bg-green-950/20",
  error:   "border-red-500/50 bg-red-950/20",
};
const STATUS_BADGE: Record<ScriptStatus, string> = {
  idle: "text-gray-500", running: "text-blue-400", done: "text-green-400", error: "text-red-400",
};
const STATUS_LABEL: Record<ScriptStatus, string> = {
  idle: "Pendiente", running: "Corriendo…", done: "Completado", error: "Error",
};

export default function Pipeline() {
  const [statuses, setStatuses] = useState<Record<string, ScriptStatus>>({});
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [advisorReport, setAdvisorReport] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const getStatus = (key: string): ScriptStatus => statuses[key] ?? "idle";

  const canRun = (script: Script) => {
    if (script.key === "parse_pdf") return !!selectedFile;
    if (!script.depends) return true;
    return getStatus(script.depends) === "done";
  };

  const setStatus = (key: string, s: ScriptStatus) =>
    setStatuses((prev) => ({ ...prev, [key]: s }));

  const appendLog = (key: string, line: string) =>
    setLogs((prev) => ({ ...prev, [key]: (prev[key] ?? "") + line + "\n" }));

  const handleParsePdf = async () => {
    if (!selectedFile) return;
    setStatus("parse_pdf", "running");
    setLogs((p) => ({ ...p, parse_pdf: "" }));
    appendLog("parse_pdf", `Subiendo ${selectedFile.name}…`);

    const form = new FormData();
    form.append("pdf", selectedFile);

    try {
      const { data } = await api.post("/snapshots/upload-pdf/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSnapshotId(data.id);
      appendLog("parse_pdf", `✅ ${data.period} — $${Number(data.total_value).toLocaleString()} — ${data.holdings_count} holdings`);
      appendLog("parse_pdf", data.created ? "Snapshot creado." : "Snapshot actualizado (ya existía).");
      setStatus("parse_pdf", "done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      appendLog("parse_pdf", `❌ Error: ${msg}`);
      setStatus("parse_pdf", "error");
    }
  };

  const handleRunScript = async (key: string, urlSuffix: string, logSuccess: (data: Record<string, unknown>) => string) => {
    if (!snapshotId) return;
    setStatus(key, "running");
    setLogs((p) => ({ ...p, [key]: "" }));
    appendLog(key, "Iniciando…");
    try {
      const { data } = await api.post(`/snapshots/${snapshotId}/${urlSuffix}/`);
      appendLog(key, logSuccess(data));
      setStatus(key, "done");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? (err instanceof Error ? err.message : String(err));
      appendLog(key, `❌ Error: ${msg}`);
      setStatus(key, "error");
    }
  };

  const handleRun = (key: string) => {
    if (key === "parse_pdf") return handleParsePdf();
    if (key === "markowitz") return handleRunScript(
      "markowitz",
      "run-markowitz",
      (d) => `✅ Markowitz completado — estrategia: ${d.primary_strategy}`,
    );
    if (key === "semaforo") return handleRunScript(
      "semaforo",
      "run-semaforo",
      (d) => `✅ Semáforo: ${d.decision} (${d.semaphore_code})\n${d.consejo}`,
    );
    if (key === "asesor") return handleRunScript(
      "asesor",
      "run-advisor",
      (d) => {
        setAdvisorReport(d.report as string);
        return `✅ Reporte generado — ${d.report_length} caracteres`;
      },
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white">Pipeline</h2>
        <p className="text-sm text-gray-500 mt-0.5">Ejecutá los scripts en orden para procesar un nuevo mes.</p>
      </div>

      {/* PDF upload zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
          selectedFile ? "border-green-600 bg-green-950/10" : "border-gray-700 hover:border-gray-600"
        }`}
        onClick={() => fileRef.current?.click()}
      >
        <p className="text-3xl mb-2">{selectedFile ? "✅" : "📄"}</p>
        {selectedFile ? (
          <>
            <p className="text-sm font-medium text-green-400">{selectedFile.name}</p>
            <p className="text-xs text-gray-500 mt-1">
              {(selectedFile.size / 1024).toFixed(0)} KB · click para cambiar
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-300">Subir estado de cuenta Alpaca</p>
            <p className="text-xs text-gray-600 mt-1">Arrastrá el PDF acá o hacé click para seleccionar</p>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setSelectedFile(f);
            setStatuses({});
            setLogs({});
            setSnapshotId(null);
          }}
        />
      </div>

      {/* Script cards */}
      <div className="space-y-3">
        {SCRIPTS.map((script) => {
          const s = getStatus(script.key);
          const disabled = !canRun(script) || s === "running" || s === "done";

          return (
            <div key={script.key} className={`border rounded-xl p-5 transition-colors ${STATUS_STYLES[s]}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <p className="text-sm font-medium text-gray-200">{script.label}</p>
                    <span className={`text-xs ${STATUS_BADGE[s]}`}>{STATUS_LABEL[s]}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{script.description}</p>
                </div>
                <button
                  onClick={() => handleRun(script.key)}
                  disabled={disabled}
                  className={`px-4 py-2 text-xs rounded-lg font-medium transition-colors flex-shrink-0 ${
                    disabled
                      ? "bg-gray-800 text-gray-600 cursor-not-allowed"
                      : "bg-green-600 text-white hover:bg-green-500"
                  }`}
                >
                  {s === "running" ? "Corriendo…" : s === "done" ? "✓ Listo" : "Ejecutar"}
                </button>
              </div>
              {logs[script.key] && (
                <pre className="mt-3 text-xs text-gray-400 bg-gray-950 rounded-lg p-3 font-mono overflow-x-auto max-h-32 overflow-y-auto">
                  {logs[script.key]}
                </pre>
              )}
            </div>
          );
        })}
      </div>

      {/* Go to dashboard once parse is done */}
      {advisorReport && (
        <AdvisorReport report={advisorReport} />
      )}

      {snapshotId && getStatus("asesor") === "done" && (
        <div className="flex justify-end">
          <button
            onClick={() => navigate("/dashboard")}
            className="px-5 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-500 transition-colors"
          >
            Ver dashboard →
          </button>
        </div>
      )}
    </div>
  );
}
