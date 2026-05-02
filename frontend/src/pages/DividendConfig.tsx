import { useEffect, useState } from "react";
import type { DividendConfig } from "../api/types";

const API_BASE = "http://localhost:8000/api";

const FREQ_OPTIONS = [
  { value: 1, label: "Mensual" },
  { value: 2, label: "Bimestral" },
  { value: 3, label: "Trimestral" },
  { value: 6, label: "Semestral" },
  { value: 12, label: "Anual" },
];

const FREQ_LABEL: Record<number, string> = {
  1: "Mensual",
  2: "Bimestral",
  3: "Trimestral",
  6: "Semestral",
  12: "Anual",
};

interface FormState {
  symbol: string;
  amount_per_share: string;
  interval_months: number;
  start_date: string;
  end_date: string;
  tax_exempt: boolean;
  notes: string;
}

const emptyForm: FormState = {
  symbol: "",
  amount_per_share: "",
  interval_months: 3,
  start_date: "",
  end_date: "",
  tax_exempt: false,
  notes: "",
};

function monthToDate(val: string): string {
  // "YYYY-MM" → "YYYY-MM-01"
  return val ? `${val}-01` : "";
}

function dateToMonth(val: string | null): string {
  // "YYYY-MM-DD" → "YYYY-MM"
  if (!val) return "";
  return val.slice(0, 7);
}

export default function DividendConfigPage() {
  const [configs, setConfigs] = useState<DividendConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchConfigs() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/dividend-configs/`);
      const data = await res.json();
      setConfigs(data);
    } catch (e) {
      setError("Error al cargar configs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchConfigs();
  }, []);

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
    setError(null);
  }

  function openEdit(cfg: DividendConfig) {
    setEditingId(cfg.id);
    setForm({
      symbol: cfg.symbol,
      amount_per_share: String(cfg.amount_per_share),
      interval_months: cfg.interval_months,
      start_date: dateToMonth(cfg.start_date),
      end_date: dateToMonth(cfg.end_date),
      tax_exempt: cfg.tax_exempt,
      notes: cfg.notes,
    });
    setShowForm(true);
    setError(null);
  }

  function cancelForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyForm);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const payload = {
      symbol: form.symbol.trim().toUpperCase(),
      amount_per_share: form.amount_per_share,
      interval_months: form.interval_months,
      start_date: monthToDate(form.start_date),
      end_date: form.end_date ? monthToDate(form.end_date) : null,
      tax_exempt: form.tax_exempt,
      notes: form.notes.trim(),
    };

    try {
      const url = editingId
        ? `${API_BASE}/dividend-configs/${editingId}/`
        : `${API_BASE}/dividend-configs/`;
      const method = editingId ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(JSON.stringify(err));
        return;
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
      await fetchConfigs();
    } catch (e) {
      setError("Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(cfg: DividendConfig) {
    if (!confirm(`¿Eliminar config de ${cfg.symbol}?`)) return;
    try {
      await fetch(`${API_BASE}/dividend-configs/${cfg.id}/`, { method: "DELETE" });
      await fetchConfigs();
    } catch {
      setError("Error al eliminar");
    }
  }

  return (
    <div className="p-6 text-gray-100 min-h-screen">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Config Dividendos</h1>
            <p className="text-sm text-gray-400 mt-1">
              La proyección en el calendario usará estos valores en lugar del promedio histórico cuando el config esté activo.
            </p>
          </div>
          {!showForm && (
            <button
              onClick={openCreate}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition-colors"
            >
              + Agregar config
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Inline Form */}
        {showForm && (
          <form
            onSubmit={handleSubmit}
            className="mb-6 p-5 bg-gray-800 border border-gray-700 rounded-xl space-y-4"
          >
            <h2 className="text-lg font-semibold text-white">
              {editingId ? "Editar config" : "Nueva config"}
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Symbol */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Symbol</label>
                <input
                  required
                  type="text"
                  value={form.symbol}
                  onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
                  placeholder="BMA"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                />
              </div>

              {/* Amount per share */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Div/Acción USD</label>
                <input
                  required
                  type="number"
                  step="0.000001"
                  min="0"
                  value={form.amount_per_share}
                  onChange={(e) => setForm({ ...form, amount_per_share: e.target.value })}
                  placeholder="0.400700"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                />
              </div>

              {/* Frecuencia */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Frecuencia</label>
                <select
                  value={form.interval_months}
                  onChange={(e) => setForm({ ...form, interval_months: Number(e.target.value) })}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                >
                  {FREQ_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Primer pago */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Primer pago</label>
                <input
                  required
                  type="month"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                />
              </div>

              {/* Último pago */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Último pago <span className="text-gray-500">(opcional)</span>
                </label>
                <input
                  type="month"
                  value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                />
              </div>

              {/* Tax exempt */}
              <div className="flex items-center gap-3 pt-5">
                <input
                  id="tax_exempt"
                  type="checkbox"
                  checked={form.tax_exempt}
                  onChange={(e) => setForm({ ...form, tax_exempt: e.target.checked })}
                  className="w-4 h-4 accent-green-500 cursor-pointer"
                />
                <label htmlFor="tax_exempt" className="text-sm text-gray-300 cursor-pointer select-none">
                  Exento de retención NRA (30%)
                  <span className="block text-xs text-gray-500">Ej: acciones argentinas como BMA, YPF</span>
                </label>
              </div>

              {/* Notas */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Notas <span className="text-gray-500">(opcional)</span>
                </label>
                <input
                  type="text"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder="Aprobado mensual desde abril"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-green-500"
                />
              </div>
            </div>

            <div className="flex gap-3 pt-1">
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
              >
                {saving ? "Guardando…" : editingId ? "Actualizar" : "Crear"}
              </button>
              <button
                type="button"
                onClick={cancelForm}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm rounded-lg transition-colors"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}

        {/* Table */}
        {loading ? (
          <p className="text-gray-400 text-sm">Cargando…</p>
        ) : configs.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <p className="text-4xl mb-3">⚙️</p>
            <p>No hay configs todavía. Agregá una para sobreescribir la proyección histórica.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-800 text-gray-400 text-left">
                  <th className="px-4 py-3 font-medium">Symbol</th>
                  <th className="px-4 py-3 font-medium">Div/Acción</th>
                  <th className="px-4 py-3 font-medium">Frecuencia</th>
                  <th className="px-4 py-3 font-medium">Primer pago</th>
                  <th className="px-4 py-3 font-medium">Último pago</th>
                  <th className="px-4 py-3 font-medium">Retención</th>
                  <th className="px-4 py-3 font-medium">Notas</th>
                  <th className="px-4 py-3 font-medium">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {configs.map((cfg) => (
                  <tr key={cfg.id} className="bg-gray-900 hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-green-400">{cfg.symbol}</td>
                    <td className="px-4 py-3 text-white">${Number(cfg.amount_per_share).toFixed(6)}</td>
                    <td className="px-4 py-3 text-gray-200">{FREQ_LABEL[cfg.interval_months] ?? `Cada ${cfg.interval_months}m`}</td>
                    <td className="px-4 py-3 text-gray-200">{cfg.start_date?.slice(0, 7)}</td>
                    <td className="px-4 py-3 text-gray-400">{cfg.end_date ? cfg.end_date.slice(0, 7) : <span className="italic">indefinido</span>}</td>
                    <td className="px-4 py-3">
                      {cfg.tax_exempt
                        ? <span className="px-2 py-0.5 text-xs rounded-full bg-green-900/40 text-green-400 border border-green-800">Exento</span>
                        : <span className="px-2 py-0.5 text-xs rounded-full bg-gray-800 text-gray-500 border border-gray-700">30% NRA</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-400 max-w-xs truncate">{cfg.notes || "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEdit(cfg)}
                          className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded transition-colors"
                        >
                          Editar
                        </button>
                        <button
                          onClick={() => handleDelete(cfg)}
                          className="px-2 py-1 text-xs bg-red-900/50 hover:bg-red-800 text-red-300 rounded transition-colors"
                        >
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
