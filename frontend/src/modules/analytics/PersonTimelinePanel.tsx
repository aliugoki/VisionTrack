import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Route, MapPin } from 'lucide-react';
import { Badge } from '@/shared/components/Badge';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useZoneDwell, usePersonTimeline } from '@/modules/analytics/api';
import type { TimelineSegment } from '@/modules/analytics/types';

/**
 * "Where was X today" — a single employee's chronological journey across zones.
 * The person picker is populated from today's dwell data (everyone seen in a
 * zone). Each row is one visit: when it started/ended, which zone, how long, and
 * whether they're still there. Refreshes every 15s so an open visit keeps
 * growing.
 */
function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s % 60}s`;
}

function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export function PersonTimelinePanel() {
  const { t } = useTranslation();
  const { data: dwell } = useZoneDwell();

  // Distinct employees seen today, sorted by display name.
  const people = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of dwell?.rows ?? []) {
      if (!map.has(r.emp_id)) map.set(r.emp_id, r.name || r.emp_id);
    }
    return [...map.entries()]
      .map(([emp_id, label]) => ({ emp_id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [dwell]);

  const [selected, setSelected] = useState<string | null>(null);

  // Default to the first person once the list arrives; keep the current choice
  // if it's still present after a refresh.
  useEffect(() => {
    if (people.length === 0) {
      setSelected(null);
    } else if (!selected || !people.some((p) => p.emp_id === selected)) {
      setSelected(people[0].emp_id);
    }
  }, [people, selected]);

  const { data: timeline, isLoading } = usePersonTimeline(selected);
  const segments: TimelineSegment[] = timeline?.segments ?? [];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <Route className="h-4 w-4" />
          {t('analytics.timeline.heading')}
        </h2>
        {people.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground" htmlFor="tl-person">
              {t('analytics.timeline.employee')}
            </label>
            <select
              id="tl-person"
              className="rounded-md border border-border bg-background px-2 py-1 text-sm"
              value={selected ?? ''}
              onChange={(e) => setSelected(e.target.value)}
            >
              {people.map((p) => (
                <option key={p.emp_id} value={p.emp_id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {people.length === 0 ? (
        <Card className="p-4 text-sm text-muted-foreground">
          {t('analytics.timeline.empty')}
        </Card>
      ) : isLoading ? (
        <Spinner />
      ) : segments.length === 0 ? (
        <Card className="p-4 text-sm text-muted-foreground">
          {t('analytics.timeline.noVisits')}
        </Card>
      ) : (
        <Card className="p-4">
          {timeline && (
            <div className="mb-3 text-xs text-muted-foreground">
              {t('analytics.timeline.summary', {
                name: timeline.name || timeline.emp_id,
                count: segments.length,
                total: formatDuration(timeline.total_seconds),
              })}
            </div>
          )}
          <ol className="relative ml-2 border-l border-border">
            {segments.map((s, i) => (
              <li key={`${s.zone_id}:${s.start}:${i}`} className="mb-4 ml-4 last:mb-0">
                <span
                  className={`absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full border-2 border-background ${
                    s.present ? 'bg-success' : 'bg-muted-foreground/50'
                  }`}
                />
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {formatClock(s.start)}
                    {' – '}
                    {s.present ? t('analytics.timeline.now') : formatClock(s.end)}
                  </span>
                  <span className="flex items-center gap-1 font-medium">
                    <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                    {s.zone_name}
                  </span>
                  {s.floor_plan_name && (
                    <span className="text-xs text-muted-foreground">
                      {s.floor_plan_name}
                    </span>
                  )}
                  <Badge tone={s.present ? 'success' : 'neutral'}>
                    {formatDuration(s.seconds)}
                  </Badge>
                  {s.present && (
                    <Badge tone="success">{t('analytics.timeline.hereNow')}</Badge>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
