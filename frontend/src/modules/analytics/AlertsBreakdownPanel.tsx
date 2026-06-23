import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useAlertsBreakdown } from '@/modules/analytics/api';
import type { BreakdownItem, DateRange } from '@/modules/analytics/types';

interface AlertsBreakdownPanelProps {
  range: DateRange;
}

/**
 * Three side-by-side horizontal bar charts: severity / zone / rule.
 *
 * One endpoint call returns all three slices. Each slice renders its
 * own top-10 horizontal bar chart.
 *
 * Layout note:
 *   - On desktop: 3 charts side-by-side in a single row
 *   - On mobile: stacks vertically (Tailwind's responsive grid)
 */
export function AlertsBreakdownPanel({ range }: AlertsBreakdownPanelProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useAlertsBreakdown(range);

  if (isLoading) {
    return (
      <Card className="flex h-48 items-center justify-center p-4">
        <Spinner size={20} />
      </Card>
    );
  }

  const hasData =
    data &&
    (data.by_severity.length > 0 ||
      data.by_zone.length > 0 ||
      data.by_rule.length > 0);

  if (!hasData) {
    return (
      <Card className="flex h-48 flex-col items-center justify-center gap-2 p-4 text-center">
        <BarChart3 className="h-6 w-6 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          {t('analytics.empty.noBreakdown')}
        </p>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <BreakdownChart
        title={t('analytics.charts.bySeverity')}
        data={data!.by_severity}
        colorFor={severityColor}
      />
      <BreakdownChart
        title={t('analytics.charts.byZone')}
        data={data!.by_zone}
        colorFor={() => '#2E9456'}
      />
      <BreakdownChart
        title={t('analytics.charts.byRule')}
        data={data!.by_rule}
        colorFor={() => '#0ea5e9'}
      />
    </div>
  );
}

function BreakdownChart({
  title,
  data,
  colorFor,
}: {
  title: string;
  data: BreakdownItem[];
  colorFor: (label: string) => string;
}) {
  const { t } = useTranslation();
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-foreground">{title}</h3>
      <div className="h-48">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            {t('analytics.empty.noBreakdownSection')}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 5, right: 10, bottom: 5, left: 5 }}
            >
              <XAxis
                type="number"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <YAxis
                dataKey="label"
                type="category"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={90}
              />
              <Tooltip
                cursor={{ fill: 'hsl(var(--muted))' }}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 6,
                  border: '1px solid hsl(var(--border))',
                  background: 'hsl(var(--card))',
                }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {data.map((item, i) => (
                  <Cell key={i} fill={colorFor(item.label)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}

function severityColor(label: string): string {
  switch (label.toLowerCase()) {
    case 'critical':
      return '#dc2626';
    case 'warning':
      return '#f59e0b';
    case 'info':
      return '#0ea5e9';
    default:
      return '#6b7280';
  }
}
