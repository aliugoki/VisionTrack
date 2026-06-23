import { useTranslation } from 'react-i18next';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Users } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { usePeopleTimeseries } from '@/modules/analytics/api';
import type { DateRange } from '@/modules/analytics/types';

interface PeopleTimeseriesChartProps {
  range: DateRange;
}

/**
 * Distinct persons tracked per time bucket — area chart.
 *
 * Why area instead of line:
 *   - People-count is a presence-style metric. Area emphasizes the
 *     "filled" volume over time, communicating activity intensity
 *     better than a flat line.
 *   - With sparse data, an area starting at zero still visually
 *     reads as a chart; a line at zero looks like an error.
 *
 * Distinct (camera_id, tracker_id) pairs counted per bucket. Same
 * physical person crossing two cameras counts twice until we have
 * ReID (Phase 3+). The label says "tracked persons" not "unique people"
 * to keep the meaning honest.
 */
export function PeopleTimeseriesChart({ range }: PeopleTimeseriesChartProps) {
  const { t } = useTranslation();
  const { data, isLoading } = usePeopleTimeseries(range);

  const chartData = (data?.points ?? []).map((p) => ({
    timestamp: p.bucket_start,
    count: p.count,
    label: formatBucket(p.bucket_start, range.bucket),
  }));

  const totalCount = chartData.reduce((acc, p) => acc + p.count, 0);
  const peakCount = chartData.reduce((max, p) => Math.max(max, p.count), 0);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">
            {t('analytics.charts.peopleOverTime')}
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          {t('analytics.charts.peakCount', { n: peakCount })}
        </span>
      </div>

      <div className="h-56">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spinner size={20} />
          </div>
        ) : totalCount === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <Users className="h-6 w-6 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              {t('analytics.empty.noPeople')}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
            >
              <defs>
                <linearGradient id="peopleGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2E9456" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#2E9456" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={30}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 6,
                  border: '1px solid hsl(var(--border))',
                  background: 'hsl(var(--card))',
                }}
                labelStyle={{ color: 'hsl(var(--foreground))' }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#2E9456"
                strokeWidth={2}
                fill="url(#peopleGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}

function formatBucket(iso: string, bucket: 'hour' | 'day'): string {
  const d = new Date(iso);
  if (bucket === 'hour') {
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
    });
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
