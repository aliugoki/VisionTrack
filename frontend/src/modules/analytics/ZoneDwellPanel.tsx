import { useTranslation } from 'react-i18next';
import { Timer } from 'lucide-react';
import { Badge } from '@/shared/components/Badge';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useZoneDwell } from '@/modules/analytics/api';
import type { ZoneDwellRow } from '@/modules/analytics/types';

/**
 * Per-person zone dwell — "indoor geofencing". For each named employee, how long
 * they've spent in each zone (department / desk) today and whether they're there
 * right now. A person's time in a zone is the sum of their tracks on the cameras
 * sitting inside that zone; "here now" means one of those tracks is still active.
 * Refreshes every 15s.
 */
function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${sec}s`;
}

function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export function ZoneDwellPanel() {
  const { t } = useTranslation();
  const { data, isLoading } = useZoneDwell();
  const rows: ZoneDwellRow[] = data?.rows ?? [];

  // Present-first, then longest dwell (backend already sorts by seconds desc).
  const sorted = [...rows].sort(
    (a, b) => Number(b.present) - Number(a.present) || b.seconds - a.seconds,
  );
  const distinctPeople = new Set(rows.map((r) => r.emp_id)).size;
  const hereNow = rows.filter((r) => r.present).length;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <Timer className="h-4 w-4" />
          {t('analytics.dwell.heading')}
        </h2>
        {rows.length > 0 && (
          <div className="flex items-center gap-2">
            <Badge tone="neutral">
              {t('analytics.dwell.peopleCount', { n: distinctPeople })}
            </Badge>
            <Badge tone="success">
              {t('analytics.dwell.hereNowCount', { n: hereNow })}
            </Badge>
          </div>
        )}
      </div>

      {isLoading ? (
        <Spinner />
      ) : sorted.length === 0 ? (
        <Card className="p-4 text-sm text-muted-foreground">
          {t('analytics.dwell.empty')}
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-semibold">
                    {t('analytics.dwell.person')}
                  </th>
                  <th className="px-4 py-2.5 text-left font-semibold">
                    {t('analytics.dwell.zone')}
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    {t('analytics.dwell.time')}
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    {t('analytics.dwell.sessions')}
                  </th>
                  <th className="px-4 py-2.5 text-left font-semibold">
                    {t('analytics.dwell.status')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr
                    key={`${r.emp_id}:${r.floor_plan_id}:${r.zone_id}`}
                    className="border-t border-border/50"
                  >
                    <td className="px-4 py-2.5 font-medium">{r.name || r.emp_id}</td>
                    <td className="px-4 py-2.5">
                      <span className="font-medium">{r.zone_name}</span>
                      {r.floor_plan_name && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {r.floor_plan_name}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums">
                      {formatDuration(r.seconds)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                      {r.sessions}
                    </td>
                    <td className="px-4 py-2.5">
                      {r.present ? (
                        <Badge tone="success">{t('analytics.dwell.hereNow')}</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {t('analytics.dwell.leftAt', { time: formatClock(r.last_seen) })}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
