import { useEffect, useState } from "react";
import api from "../api/client";
import type {
  DividendCalendarResponse,
  DividendCalendarRow,
  DividendCalendarMonth,
  DividendMonthCell,
  DividendScheduleEntry,
} from "../api/types";

function fmt(n: number) {
  return `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function SummaryCard({ label, value, sub, color = "text-gray-900 dark:text-white" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function DivCell({ cell }: { cell: DividendMonthCell }) {
  if (cell.projected) {
    return (
      <div className="text-right py-2 px-3">
        <p className="text-sm font-medium text-gray-400 dark:text-gray-500 italic">{fmt(cell.net)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-600 mt-0.5">{fmt(cell.gross)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-600">{fmt(cell.withheld)}</p>
      </div>
    );
  }
  return (
    <div className="text-right py-2 px-3">
      <p className="text-sm font-semibold text-green-600 dark:text-green-400">{fmt(cell.net)}</p>
      <p className="text-xs text-gray-500 mt-0.5">{fmt(cell.gross)}</p>
      <p className="text-xs text-red-500/70 dark:text-red-400/70">{fmt(cell.withheld)}</p>
    </div>
  );
}

function TotalCell({ gross, withheld, projected }: { gross: number; withheld: number; projected: boolean }) {
  const net = gross + withheld;
  if (projected) {
    return (
      <div className="text-right py-2 px-3">
        <p className="text-sm font-semibold text-gray-400 dark:text-gray-500 italic">{fmt(net)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-600">{fmt(gross)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-600">{fmt(withheld)}</p>
      </div>
    );
  }
  return (
    <div className="text-right py-2 px-3">
      <p className="text-sm font-semibold text-green-600 dark:text-green-400">{fmt(net)}</p>
      <p className="text-xs text-gray-500">{fmt(gross)}</p>
      <p className="text-xs text-red-500/70 dark:text-red-400/70">{fmt(withheld)}</p>
    </div>
  );
}

function YearTable({
  year,
  months,
  rows,
  totals,
  inTab = false,
}: {
  year: number;
  months: DividendCalendarMonth[];
  rows: DividendCalendarRow[];
  totals: DividendCalendarResponse["totals"];
  inTab?: boolean;
}) {
  const hasReal = months.some((m) => !m.projected);
  const hasProj = months.some((m) => m.projected);

  let yearRealGross = 0, yearRealWithheld = 0;
  let yearProjGross = 0, yearProjWithheld = 0;
  for (const m of months) {
    const mt = totals.by_month[m.period_date];
    if (!mt) continue;
    if (m.projected) { yearProjGross += mt.gross; yearProjWithheld += mt.withheld; }
    else              { yearRealGross += mt.gross; yearRealWithheld += mt.withheld; }
  }

  const inner = (
    <>
      {/* Sub-header with year totals */}
      <div className="px-5 py-2.5 border-b border-gray-200 dark:border-gray-800 flex items-center gap-4 text-xs bg-gray-50/60 dark:bg-gray-900/60">
        {hasReal && (
          <span className="text-green-600 dark:text-green-400">
            Real: <span className="font-semibold">{fmt(yearRealGross + yearRealWithheld)}</span>
            <span className="text-gray-500 ml-1">(bruto {fmt(yearRealGross)} · ret. {fmt(yearRealWithheld)})</span>
          </span>
        )}
        {hasProj && (
          <span className="text-gray-400 dark:text-gray-500 italic">
            Proyectado: <span className="font-semibold">{fmt(yearProjGross + yearProjWithheld)}</span>
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="text-sm w-full">
          <thead>
            <tr className="text-xs uppercase tracking-wider border-b border-gray-300 dark:border-gray-700">
              <th className="px-5 py-3 text-left sticky left-0 bg-gray-50 dark:bg-gray-900 z-10 min-w-[80px] text-gray-500">Ticker</th>
              {months.map((m) => (
                <th
                  key={m.period_date}
                  className={`px-3 py-3 text-right min-w-[110px] font-medium ${
                    m.projected ? "text-gray-400 dark:text-gray-600 italic" : "text-gray-500 dark:text-gray-400"
                  }`}
                >
                  {m.label.split(" ")[0]}
                  {m.projected && <span className="ml-1 text-gray-300 dark:text-gray-700 not-italic">~</span>}
                </th>
              ))}
              <th className="px-4 py-3 text-right min-w-[115px] border-l-2 border-gray-300 dark:border-gray-600 bg-gray-100/60 dark:bg-gray-800/60 text-green-600/80 dark:text-green-500/80 font-semibold">
                Total Real
              </th>
              {hasProj && (
                <th className="px-4 py-3 text-right min-w-[115px] bg-gray-100/30 dark:bg-gray-800/30 text-gray-400 dark:text-gray-500 italic font-medium">
                  Total Proy.
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const hasAnyInYear = months.some((m) => row.months[m.period_date]);
              if (!hasAnyInYear) return null;

              let rowRealG = 0, rowRealW = 0, rowProjG = 0, rowProjW = 0;
              for (const m of months) {
                const cell = row.months[m.period_date];
                if (!cell) continue;
                if (m.projected) { rowProjG += cell.gross; rowProjW += cell.withheld; }
                else              { rowRealG += cell.gross; rowRealW += cell.withheld; }
              }

              return (
                <tr key={row.symbol} className="border-b border-gray-200/40 dark:border-gray-800/40 hover:bg-gray-100/20 dark:hover:bg-gray-800/20 transition-colors">
                  <td className="px-5 py-2 font-mono font-medium text-gray-800 dark:text-gray-100 sticky left-0 bg-gray-50 dark:bg-gray-900 z-10">
                    {row.symbol}
                  </td>
                  {months.map((m) => {
                    const cell = row.months[m.period_date];
                    return (
                      <td
                        key={m.period_date}
                        className={`border-l border-gray-200/20 dark:border-gray-800/20 ${m.projected ? "bg-white/60 dark:bg-gray-950/60" : ""}`}
                      >
                        {cell ? <DivCell cell={cell} /> : (
                          <div className="text-center py-2 px-3 text-gray-300 dark:text-gray-700 text-sm">—</div>
                        )}
                      </td>
                    );
                  })}
                  {/* Total Real column */}
                  <td className="border-l-2 border-gray-300 dark:border-gray-600 bg-gray-100/50 dark:bg-gray-800/50 px-4 py-2 text-right">
                    {rowRealG > 0 ? (
                      <div>
                        <p className="text-sm font-bold text-green-600 dark:text-green-400">{fmt(rowRealG + rowRealW)}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{fmt(rowRealG)}</p>
                        <p className="text-xs text-red-500/70 dark:text-red-400/70">{fmt(rowRealW)}</p>
                      </div>
                    ) : <span className="text-gray-300 dark:text-gray-700 text-sm">—</span>}
                  </td>
                  {/* Total Proyectado column */}
                  {hasProj && (
                    <td className="bg-gray-100/20 dark:bg-gray-800/20 px-4 py-2 text-right">
                      {rowProjG > 0 ? (
                        <div>
                          <p className="text-sm font-semibold text-gray-400 dark:text-gray-500 italic">{fmt(rowProjG + rowProjW)}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-600">{fmt(rowProjG)}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-600">{fmt(rowProjW)}</p>
                        </div>
                      ) : <span className="text-gray-300 dark:text-gray-700 text-sm">—</span>}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-xs">
              <td className="px-5 py-3 font-bold text-gray-900 dark:text-white tracking-wider uppercase sticky left-0 bg-gray-100 dark:bg-gray-800 z-10">
                Total
              </td>
              {months.map((m) => {
                const mt = totals.by_month[m.period_date];
                return (
                  <td
                    key={m.period_date}
                    className={`border-l border-gray-300/40 dark:border-gray-700/40 ${m.projected ? "bg-gray-50/40 dark:bg-gray-900/40" : ""}`}
                  >
                    {mt && (mt.gross !== 0 || mt.withheld !== 0)
                      ? <TotalCell gross={mt.gross} withheld={mt.withheld} projected={m.projected} />
                      : <div className="text-center py-2 px-3 text-gray-400 dark:text-gray-600">—</div>}
                  </td>
                );
              })}
              {/* Grand total real */}
              <td className="border-l-2 border-gray-300 dark:border-gray-600 bg-gray-200/60 dark:bg-gray-700/60 px-4 py-2 text-right">
                {yearRealGross > 0 && (
                  <div>
                    <p className="text-sm font-bold text-green-600 dark:text-green-300">{fmt(yearRealGross + yearRealWithheld)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{fmt(yearRealGross)}</p>
                    <p className="text-xs text-red-500/70 dark:text-red-400/70">{fmt(yearRealWithheld)}</p>
                  </div>
                )}
              </td>
              {/* Grand total projected */}
              {hasProj && (
                <td className="bg-gray-200/30 dark:bg-gray-700/30 px-4 py-2 text-right">
                  {yearProjGross > 0 && (
                    <div>
                      <p className="text-sm font-bold text-gray-500 dark:text-gray-400 italic">{fmt(yearProjGross + yearProjWithheld)}</p>
                      <p className="text-xs text-gray-500">{fmt(yearProjGross)}</p>
                      <p className="text-xs text-gray-500">{fmt(yearProjWithheld)}</p>
                    </div>
                  )}
                </td>
              )}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  );

  if (inTab) return inner;
  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
      {inner}
    </div>
  );
}

function fmtDate(d: string | null) {
  if (!d) return "—";
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
}

function daysUntil(d: string | null): number | null {
  if (!d) return null;
  const diff = new Date(d).getTime() - Date.now();
  return Math.ceil(diff / 86400000);
}

function ScheduleTable({ schedule, today }: { schedule: DividendScheduleEntry[]; today: string }) {
  const upcoming = schedule.filter((s) => s.next_ex_date && s.next_ex_date >= today);
  const past = schedule.filter((s) => !s.next_ex_date || s.next_ex_date < today);

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
        <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Fechas de dividendos</p>
        <p className="text-xs text-gray-400 dark:text-gray-600 mt-0.5">
          Ex-date: último día para comprar y recibir el dividendo · Proyecciones basadas en historial
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-200 dark:border-gray-800">
              <th className="px-5 py-3 text-left">Ticker</th>
              <th className="px-4 py-3 text-left">Frecuencia</th>
              <th className="px-4 py-3 text-right">Div/Acción</th>
              <th className="px-4 py-3 text-right">Último Ex-Date</th>
              <th className="px-4 py-3 text-right">Último Pago</th>
              <th className="px-4 py-3 text-right border-l border-gray-300 dark:border-gray-700 text-yellow-600/80 dark:text-yellow-500/80">Próx. Ex-Date ~</th>
              <th className="px-4 py-3 text-right text-yellow-600/80 dark:text-yellow-500/80">Próx. Pago ~</th>
              <th className="px-4 py-3 text-right text-yellow-600/80 dark:text-yellow-500/80">Faltan</th>
            </tr>
          </thead>
          <tbody>
            {upcoming.map((s) => {
              const days = daysUntil(s.next_ex_date);
              const urgent = days !== null && days <= 7;
              const soon = days !== null && days <= 30;
              return (
                <tr key={s.symbol} className={`border-b border-gray-200/50 dark:border-gray-800/50 transition-colors ${urgent ? "bg-yellow-900/10 hover:bg-yellow-900/20" : "hover:bg-gray-100/30 dark:hover:bg-gray-800/30"}`}>
                  <td className="px-5 py-3 font-mono font-medium text-gray-800 dark:text-gray-100">{s.symbol}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{s.frequency}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-mono">
                    {s.last_div_per_share != null ? `$${s.last_div_per_share.toFixed(4)}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-500 text-xs">{fmtDate(s.last_ex_date)}</td>
                  <td className="px-4 py-3 text-right text-gray-500 text-xs">{fmtDate(s.last_pay_date)}</td>
                  <td className={`px-4 py-3 text-right font-medium border-l border-gray-300 dark:border-gray-700 text-xs ${urgent ? "text-yellow-600 dark:text-yellow-400" : soon ? "text-yellow-500/80" : "text-gray-600 dark:text-gray-300"}`}>
                    {fmtDate(s.next_ex_date)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-500 text-xs">{fmtDate(s.next_pay_date)}</td>
                  <td className="px-4 py-3 text-right text-xs">
                    {days !== null ? (
                      <span className={`px-2 py-0.5 rounded-full ${urgent ? "bg-yellow-500/20 text-yellow-600 dark:text-yellow-400" : soon ? "bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300" : "text-gray-500"}`}>
                        {days}d
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              );
            })}
            {past.map((s) => (
              <tr key={s.symbol} className="border-b border-gray-200/30 dark:border-gray-800/30 hover:bg-gray-100/20 dark:hover:bg-gray-800/20 transition-colors opacity-50">
                <td className="px-5 py-3 font-mono font-medium text-gray-500 dark:text-gray-400">{s.symbol}</td>
                <td className="px-4 py-3 text-gray-400 dark:text-gray-600 text-xs">{s.frequency}</td>
                <td className="px-4 py-3 text-right text-gray-400 dark:text-gray-600 font-mono text-xs">
                  {s.last_div_per_share != null ? `$${s.last_div_per_share.toFixed(4)}` : "—"}
                </td>
                <td className="px-4 py-3 text-right text-gray-400 dark:text-gray-600 text-xs">{fmtDate(s.last_ex_date)}</td>
                <td className="px-4 py-3 text-right text-gray-400 dark:text-gray-600 text-xs">{fmtDate(s.last_pay_date)}</td>
                <td className="px-4 py-3 text-right text-gray-400 dark:text-gray-600 text-xs border-l border-gray-200 dark:border-gray-800" colSpan={3}>
                  sin próx. pago proyectado este año
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Dividends() {
  const [data, setData] = useState<DividendCalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const today = new Date().toISOString().slice(0, 10);
  const [activeYear, setActiveYear] = useState<number | null>(null);

  useEffect(() => {
    api.get<DividendCalendarResponse>("/snapshots/dividends-calendar/")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-gray-500 text-sm">Cargando dividendos…</div>;
  if (!data || data.rows.length === 0) return <div className="p-6 text-gray-500 text-sm">No hay datos de dividendos aún.</div>;

  const { months, rows, totals } = data;

  const byYear = months.reduce<Record<number, DividendCalendarMonth[]>>((acc, m) => {
    const y = new Date(m.period_date).getUTCFullYear();
    (acc[y] ??= []).push(m);
    return acc;
  }, {});
  const years = Object.keys(byYear).map(Number).sort();
  const selectedYear = activeYear ?? years[years.length - 1];

  const projectedNet = totals.proj_gross + totals.proj_withheld;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Dividendos</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Montos reales de PDFs Alpaca · Meses con ~ son proyecciones basadas en el historial
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          label="Neto Cobrado"
          value={fmt(totals.real_net)}
          sub={`bruto ${fmt(totals.real_gross)}`}
          color="text-green-600 dark:text-green-400"
        />
        <SummaryCard
          label="Retenido (NRA 30%)"
          value={fmt(totals.real_withheld)}
          color="text-red-600 dark:text-red-400"
        />
        <SummaryCard
          label="Proyectado Neto (resto del año)"
          value={fmt(projectedNet)}
          sub={`bruto ${fmt(totals.proj_gross)}`}
          color="text-gray-500 dark:text-gray-400"
        />
        <SummaryCard
          label="Total Año (real + proy.)"
          value={fmt(totals.real_net + projectedNet)}
        />
      </div>

      {/* Year tabs + table */}
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        {/* Tab bar */}
        <div className="flex border-b border-gray-200 dark:border-gray-800">
          {years.map((year) => {
            const yMonths = byYear[year];
            const hasReal = yMonths.some((m) => !m.projected);
            const hasProj = yMonths.some((m) => m.projected);
            return (
              <button
                key={year}
                onClick={() => setActiveYear(year)}
                className={`px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
                  selectedYear === year
                    ? "border-green-500 text-green-600 dark:text-green-400"
                    : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                {year}
                {hasReal && hasProj && (
                  <span className="ml-2 text-xs text-gray-400 dark:text-gray-600">real + ~</span>
                )}
                {hasProj && !hasReal && (
                  <span className="ml-2 text-xs text-gray-400 dark:text-gray-600">~</span>
                )}
              </button>
            );
          })}
        </div>

        <YearTable
          year={selectedYear}
          months={byYear[selectedYear]}
          rows={rows}
          totals={totals}
          inTab
        />
      </div>

      {/* Schedule table */}
      <ScheduleTable schedule={data.schedule} today={today} />

      {/* Legend */}
      <div className="flex items-center gap-6 text-xs text-gray-400 dark:text-gray-600 px-1">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
          Monto real (del informe Alpaca)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />
          Proyección (promedio histórico · columnas con ~)
        </span>
        <span>Cada celda: neto · bruto · retención</span>
      </div>
    </div>
  );
}
