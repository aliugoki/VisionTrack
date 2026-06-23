import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Bell } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useAlertsTimeseries } from '@/modules/analytics/api';
import type { DateRange } from '@/modules/analytics/types';

interface AlertsTimeseriesChartProps {
  range: DateRange;
}

/**
 * Line chart of alert counts per time bucket.
 *
 * The bucket size (hour/day) is determined by the parent's range and
 * just passed through here. Bucket starts are server-side rendered as
 * ISO datetimes; we localize on the client for axis labels.
 *
 * Empty state: when no alerts in the period, render a centered hint
 * instead of an empty axis grid.
 */
export function AlertsTimeseriesChart({ range }: AlertsTimeseriesChartProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useAlertsTimeseries(range);

  // Prepare chart data — Recharts wants numeric x-axis or simple labels
  const chartData = (data?.points ?? []).map((p) => ({
    timestamp: p.bucket_start,
    count: p.count,
    label: formatBucket(p.bucket_start, range.bucket),
  }));

  const totalCount = chartData.reduce((acc, p) => acc + p.count, 0);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">
            {t('analytics.charts.alertsOverTime')}
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          {t('analytics.charts.totalAlerts', { n: totalCount })}
        </span>
      </div>

      <div className="h-56">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spinner size={20} />
          </div>
        ) : totalCount === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <Bell className="h-6 w-6 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              {t('analytics.empty.noAlerts')}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
            >
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
              <Line
                type="monotone"
                dataKey="count"
                stroke="#2E9456"
                strokeWidth={2}
                dot={chartData.length <= 30 ? { r: 2.5 } : false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
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
