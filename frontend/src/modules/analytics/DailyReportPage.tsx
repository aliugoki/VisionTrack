import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Printer, ArrowLeft } from 'lucide-react';
import { Spinner } from '@/shared/components/Spinner';
import { useZoneDwell, usePersonTimeline } from '@/modules/analytics/api';

/**
 * Print-friendly daily zone report — a bare, chrome-less route (mounted outside
 * AppLayout) that renders a clean white document and lets the browser "Save as
 * PDF". Section 1 is the per-employee time-in-zone summary; then one movement
 * timeline per employee. Screen-only controls carry `print:hidden`.
 *
 * Range: `?date=YYYY-MM-DD` (that UTC day); default is today (start of day -> now).
 */
function dayRange(dateStr: string | null): { from: string; to: string; label: string } {
  if (dateStr && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const start = new Date(`${dateStr}T00:00:00.000Z`);
    const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
    return { from: start.toISOString(), to: end.toISOString(), label: dateStr };
  }
  const now = new Date();
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  return { from: start.toISOString(), to: now.toISOString(), label: start.toISOString().slice(0, 10) };
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
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export default function DailyReportPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { from, to, label } = useMemo(() => dayRange(params.get('date')), [params]);

  const { data, isLoading } = useZoneDwell({ from, to });
  const rows = data?.rows ?? [];

  // Distinct employees seen, sorted by display name.
  const people = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of rows) if (!map.has(r.emp_id)) map.set(r.emp_id, r.name || r.emp_id);
    return [...map.entries()]
      .map(([emp_id, name]) => ({ emp_id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  const summary = useMemo(
    () => [...rows].sort((a, b) => (a.name || a.emp_id).localeCompare(b.name || b.emp_id) || b.seconds - a.seconds),
    [rows],
  );

  return (
    <div className="mx-auto min-h-screen max-w-4xl bg-white p-8 text-black print:p-0">
      <style>{'@page { margin: 14mm; } @media print { html, body { background: #fff; } }'}</style>

      {/* Screen-only toolbar */}
      <div className="mb-6 flex items-center justify-between print:hidden">
        <button
          type="button"
          onClick={() => window.close()}
          className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('common.back')}
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

      {/* Document header */}
      <header className="mb-6 border-b border-gray-300 pb-4">
        <h1 className="text-2xl font-bold">{t('analytics.report.title')}</h1>
        <p className="mt-1 text-sm text-gray-600">
          {label} · {t('analytics.report.generated', { ts: new Date().toLocaleString() })}
        </p>
      </header>

      {isLoading ? (
        <Spinner />
      ) : summary.length === 0 ? (
        <p className="text-sm text-gray-600">{t('analytics.report.noData')}</p>
      ) : (
        <>
          {/* Summary table */}
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

          {/* Per-employee movement timelines */}
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
              {t('analytics.report.movementHeading')}
            </h2>
            {people.map((p) => (
              <EmployeeTimelineSection key={p.emp_id} empId={p.emp_id} name={p.name} from={from} to={to} />
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
}: {
  empId: string;
  name: string;
  from: string;
  to: string;
}) {
  const { t } = useTranslation();
  const { data } = usePersonTimeline(empId, { from, to });
  const segs = data?.segments ?? [];
  if (segs.length === 0) return null;

  return (
    <div className="mb-5 break-inside-avoid">
      <h3 className="mb-1 flex items-baseline justify-between border-b border-gray-200 pb-1">
        <span className="font-semibold">{name}</span>
        <span className="text-xs text-gray-500">
          {t('analytics.report.total', { time: fmtDuration(data?.total_seconds ?? 0) })}
        </span>
      </h3>
      <ol className="mt-1 space-y-0.5 text-sm">
        {segs.map((s, i) => (
          <li key={`${s.zone_id}:${s.start}:${i}`} className="flex items-center gap-2">
            <span className="w-28 shrink-0 font-mono text-xs tabular-nums text-gray-600">
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
