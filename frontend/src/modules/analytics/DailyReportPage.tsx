import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Printer, X, Download, Filter } from 'lucide-react';
import { Spinner } from '@/shared/components/Spinner';
import {
  useZoneDwell,
  usePersonTimeline,
  downloadDwellCsv,
} from '@/modules/analytics/api';

/**
 * Print-friendly zone report — a bare, chrome-less route (mounted outside
 * AppLayout) that renders a clean white document and lets the browser "Save as
 * PDF". A screen-only filter bar (date range, employee, zone, min minutes)
 * narrows the report and is reflected in the printed header; all filters live in
 * the URL so a filtered report is shareable/bookmarkable. Section 1 is the
 * per-employee time-in-zone summary; then one movement timeline per employee.
 *
 * Range params: `?from=YYYY-MM-DD&to=YYYY-MM-DD` (inclusive). Back-compat: a
 * single `?date=YYYY-MM-DD` is treated as from=to=date. No params -> today.
 */
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function ymd(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function addDays(dateStr: string, n: number): string {
  const d = new Date(`${dateStr}T00:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return ymd(d);
}
function startOfMonth(dateStr: string): string {
  return `${dateStr.slice(0, 7)}-01`;
}

interface Range {
  fromIso: string;
  toIso: string;
  fromDate: string;
  toDate: string;
  label: string;
}

function resolveRange(params: URLSearchParams): Range {
  const today = ymd(new Date());
  const fromP = params.get('from');
  const toP = params.get('to');
  const single = params.get('date');

  let fromDate: string;
  let toDate: string;
  if (fromP && DATE_RE.test(fromP)) {
    fromDate = fromP;
    toDate = toP && DATE_RE.test(toP) ? toP : fromP;
  } else if (single && DATE_RE.test(single)) {
    fromDate = single;
    toDate = single;
  } else {
    fromDate = today;
    toDate = today;
  }
  if (toDate < fromDate) [fromDate, toDate] = [toDate, fromDate];

  const start = new Date(`${fromDate}T00:00:00.000Z`);
  const end = new Date(`${addDays(toDate, 1)}T00:00:00.000Z`); // exclusive upper bound
  return {
    fromIso: start.toISOString(),
    toIso: end.toISOString(),
    fromDate,
    toDate,
    label: fromDate === toDate ? fromDate : `${fromDate} → ${toDate}`,
  };
}

function fmtDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s % 60}s`;
}

function fmtClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function DailyReportPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();

  const emp = params.get('emp') || '';
  const zone = params.get('zone') || '';
  const minMinutes = Math.max(0, Number(params.get('min') || '0') || 0);
  const minSec = minMinutes * 60;

  const range = useMemo(() => resolveRange(params), [params]);
  const { fromIso, toIso, fromDate, toDate, label } = range;

  const { data, isLoading } = useZoneDwell({ from: fromIso, to: toIso });
  const allRows = data?.rows ?? [];

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }
  function setRange(f: string, to: string) {
    const next = new URLSearchParams(params);
    next.delete('date');
    next.set('from', f);
    next.set('to', to);
    setParams(next, { replace: true });
  }

  const today = ymd(new Date());
  const presets = [
    { key: 'today', from: today, to: today },
    { key: 'yesterday', from: addDays(today, -1), to: addDays(today, -1) },
    { key: 'last7', from: addDays(today, -6), to: today },
    { key: 'last30', from: addDays(today, -29), to: today },
    { key: 'thisMonth', from: startOfMonth(today), to: today },
  ];

  const empOptions = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of allRows) if (!m.has(r.emp_id)) m.set(r.emp_id, r.name || r.emp_id);
    return [...m.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [allRows]);

  const zoneOptions = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of allRows) if (!m.has(r.zone_id)) m.set(r.zone_id, r.zone_name);
    return [...m.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [allRows]);

  const rows = useMemo(
    () =>
      allRows.filter(
        (r) =>
          (!emp || r.emp_id === emp) &&
          (!zone || r.zone_id === zone) &&
          r.seconds >= minSec,
      ),
    [allRows, emp, zone, minSec],
  );

  const people = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of rows) if (!m.has(r.emp_id)) m.set(r.emp_id, r.name || r.emp_id);
    return [...m.entries()].map(([id, name]) => ({ emp_id: id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  const summary = useMemo(
    () => [...rows].sort((a, b) => (a.name || a.emp_id).localeCompare(b.name || b.emp_id) || b.seconds - a.seconds),
    [rows],
  );

  const hasFilters = !!emp || !!zone || minMinutes > 0;
  const activeFilterText = [
    emp && `${t('analytics.dwell.person')}: ${empOptions.find((o) => o.id === emp)?.name || emp}`,
    zone && `${t('analytics.dwell.zone')}: ${zoneOptions.find((o) => o.id === zone)?.name || zone}`,
    minMinutes > 0 && t('analytics.report.minLabel', { n: minMinutes }),
  ]
    .filter(Boolean)
    .join(' · ');

  const inputCls = 'rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-gray-800';

  return (
    <div className="mx-auto min-h-screen max-w-4xl bg-white p-8 text-black print:p-0">
      <style>{'@page { margin: 14mm; } @media print { html, body { background: #fff; } }'}</style>

      {/* Screen-only toolbar */}
      <div className="mb-4 flex items-center justify-between print:hidden">
        <button
          type="button"
          onClick={() => window.close()}
          className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
        >
          <X className="h-4 w-4" />
          {t('common.close')}
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() =>
              downloadDwellCsv({
                from: fromIso,
                to: toIso,
                minSeconds: minSec || undefined,
                empId: emp || undefined,
                zoneId: zone || undefined,
              }).catch(() => toast.error(t('common.exportFailed')))
            }
            className="flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
          >
            <Download className="h-4 w-4" />
            {t('common.exportCsv')}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="flex items-center gap-1.5 rounded-md bg-gray-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-gray-700"
          >
            <Printer className="h-4 w-4" />
            {t('analytics.report.print')}
          </button>
        </div>
      </div>

      {/* Screen-only filter bar */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5 print:hidden">
        {presets.map((p) => {
          const active = fromDate === p.from && toDate === p.to;
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => setRange(p.from, p.to)}
              className={`rounded-md border px-2 py-1 text-xs ${
                active
                  ? 'border-gray-800 bg-gray-900 text-white'
                  : 'border-gray-300 text-gray-600 hover:bg-gray-100'
              }`}
            >
              {t(`analytics.report.range.${p.key}`)}
            </button>
          );
        })}
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2 rounded-md border border-gray-200 bg-gray-50 p-2 print:hidden">
        <span className="flex items-center gap-1 text-xs font-semibold text-gray-500">
          <Filter className="h-3.5 w-3.5" />
          {t('analytics.report.filters')}
        </span>
        <label className="flex items-center gap-1 text-sm text-gray-700">
          {t('analytics.report.from')}
          <input type="date" className={inputCls} value={fromDate} onChange={(e) => setRange(e.target.value, toDate)} />
        </label>
        <label className="flex items-center gap-1 text-sm text-gray-700">
          {t('analytics.report.to')}
          <input type="date" className={inputCls} value={toDate} onChange={(e) => setRange(fromDate, e.target.value)} />
        </label>
        <select className={inputCls} value={emp} onChange={(e) => setFilter('emp', e.target.value)}>
          <option value="">{t('analytics.report.allEmployees')}</option>
          {empOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        <select className={inputCls} value={zone} onChange={(e) => setFilter('zone', e.target.value)}>
          <option value="">{t('analytics.report.allZones')}</option>
          {zoneOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-sm text-gray-700">
          {t('analytics.report.minMinutes')}
          <input
            type="number"
            min={0}
            className={`${inputCls} w-16`}
            value={minMinutes || ''}
            onChange={(e) => setFilter('min', e.target.value)}
          />
        </label>
        {hasFilters && (
          <button
            type="button"
            onClick={() => setRange(fromDate, toDate)}
            className="rounded-md px-2 py-1 text-xs text-gray-500 underline hover:text-gray-800"
          >
            {t('analytics.report.reset')}
          </button>
        )}
      </div>

      {/* Document header */}
      <header className="mb-6 border-b border-gray-300 pb-4">
        <h1 className="text-2xl font-bold">{t('analytics.report.title')}</h1>
        <p className="mt-1 text-sm text-gray-600">
          {label} · {t('analytics.report.generated', { ts: new Date().toLocaleString() })}
        </p>
        {hasFilters && <p className="mt-0.5 text-sm text-gray-600">{activeFilterText}</p>}
      </header>

      {isLoading ? (
        <Spinner />
      ) : summary.length === 0 ? (
        <p className="text-sm text-gray-600">{t('analytics.report.noData')}</p>
      ) : (
        <>
          <section className="mb-8">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
              {t('analytics.report.summaryHeading')}
            </h2>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b-2 border-gray-400 text-left">
                  <th className="py-1.5 pr-3 font-semibold">{t('analytics.dwell.person')}</th>
                  <th className="py-1.5 pr-3 font-semibold">{t('analytics.dwell.zone')}</th>
                  <th className="py-1.5 pr-3 text-right font-semibold">{t('analytics.dwell.time')}</th>
                  <th className="py-1.5 pr-3 text-right font-semibold">{t('analytics.dwell.sessions')}</th>
                  <th className="py-1.5 font-semibold">{t('analytics.dwell.status')}</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((r) => (
                  <tr
                    key={`${r.emp_id}:${r.floor_plan_id}:${r.zone_id}`}
                    className="break-inside-avoid border-b border-gray-200"
                  >
                    <td className="py-1.5 pr-3">{r.name || r.emp_id}</td>
                    <td className="py-1.5 pr-3">
                      {r.zone_name}
                      {r.floor_plan_name && <span className="text-gray-500"> · {r.floor_plan_name}</span>}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-medium tabular-nums">
                      {fmtDuration(r.seconds)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{r.sessions}</td>
                    <td className="py-1.5">
                      {r.present
                        ? t('analytics.dwell.hereNow')
                        : t('analytics.dwell.leftAt', { time: fmtClock(r.last_seen) })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
              {t('analytics.report.movementHeading')}
            </h2>
            {people.map((p) => (
              <EmployeeTimelineSection
                key={p.emp_id}
                empId={p.emp_id}
                name={p.name}
                from={fromIso}
                to={toIso}
                zoneId={zone}
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function EmployeeTimelineSection({
  empId,
  name,
  from,
  to,
  zoneId,
}: {
  empId: string;
  name: string;
  from: string;
  to: string;
  zoneId?: string;
}) {
  const { t } = useTranslation();
  const { data } = usePersonTimeline(empId, { from, to });
  const segs = (data?.segments ?? []).filter((s) => !zoneId || s.zone_id === zoneId);
  if (segs.length === 0) return null;
  const total = segs.reduce((sum, s) => sum + s.seconds, 0);

  return (
    <div className="mb-5 break-inside-avoid">
      <h3 className="mb-1 flex items-baseline justify-between border-b border-gray-200 pb-1">
        <span className="font-semibold">{name}</span>
        <span className="text-xs text-gray-500">
          {t('analytics.report.total', { time: fmtDuration(total) })}
        </span>
      </h3>
      <ol className="mt-1 space-y-0.5 text-sm">
        {segs.map((s, i) => (
          <li key={`${s.zone_id}:${s.start}:${i}`} className="flex items-center gap-2">
            <span className="w-36 shrink-0 font-mono text-xs tabular-nums text-gray-600">
              {fmtClock(s.start)} – {s.present ? t('analytics.timeline.now') : fmtClock(s.end)}
            </span>
            <span className="font-medium">{s.zone_name}</span>
            <span className="text-xs text-gray-500">{fmtDuration(s.seconds)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
