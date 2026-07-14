import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Clapperboard,
  Map as MapIcon,
  Users,
  UserCircle2,
  UserPlus,
  Sparkles,
  Repeat,
} from 'lucide-react';
import { AlertsBreakdownPanel } from '@/modules/analytics/AlertsBreakdownPanel';
import { AlertsTimeseriesChart } from '@/modules/analytics/AlertsTimeseriesChart';
import { DateRangePicker } from '@/modules/analytics/DateRangePicker';
import { KpiCard } from '@/modules/analytics/KpiCard';
import { PeopleTimeseriesChart } from '@/modules/analytics/PeopleTimeseriesChart';
import { ZoneOccupancyPanel } from '@/modules/analytics/ZoneOccupancyPanel';
import { ZoneDwellPanel } from '@/modules/analytics/ZoneDwellPanel';
import { useOverview, usePersonsSummary } from '@/modules/analytics/api';
import type { DateRange } from '@/modules/analytics/types';

export default function AnalyticsPage() {
  const { t } = useTranslation();

  // Default: last 7 days, day-bucketed
  const [range, setRange] = useState<DateRange>(() => {
    const now = new Date();
    const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      from: from.toISOString(),
      to: now.toISOString(),
      bucket: 'day',
    };
  });

  const { data: overview, isLoading: overviewLoading } = useOverview(range);
  const { data: personsSummary, isLoading: personsLoading } = usePersonsSummary();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <BarChart3 className="h-6 w-6" />
            {t('analytics.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('analytics.subtitle')}
          </p>
        </div>
        <DateRangePicker value={range} onChange={setRange} />
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={Bell}
          label={t('analytics.kpi.alertsTotal')}
          value={overviewLoading ? '—' : (overview?.alerts_total ?? 0).toLocaleString()}
          tone="default"
        />
        <KpiCard
          icon={AlertTriangle}
          label={t('analytics.kpi.alertsActive')}
          value={overviewLoading ? '—' : (overview?.alerts_active ?? 0).toLocaleString()}
          tone={(overview?.alerts_active ?? 0) > 0 ? 'warning' : 'default'}
        />
        <KpiCard
          icon={MapIcon}
          label={t('analytics.kpi.zonesWithAlerts')}
          value={overviewLoading ? '—' : (overview?.distinct_zones_with_alerts ?? 0).toLocaleString()}
          tone="default"
        />
        <KpiCard
          icon={Users}
          label={t('analytics.kpi.personsTracked')}
          value={overviewLoading ? '—' : (overview?.distinct_persons_tracked ?? 0).toLocaleString()}
          tone="success"
        />
      </div>

      {/* Identities row — cross-camera Person identities from the matcher */}
      <div>
        <h2 className="mb-2 mt-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          <UserCircle2 className="h-3.5 w-3.5" />
          {t('analytics.identities.heading')}
        </h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            icon={UserCircle2}
            label={t('analytics.identities.total')}
            value={personsLoading ? '—' : (personsSummary?.total_identities ?? 0).toLocaleString()}
            tone="default"
          />
          <KpiCard
            icon={Sparkles}
            label={t('analytics.identities.activeLast24h')}
            value={personsLoading ? '—' : (personsSummary?.active_last_24h ?? 0).toLocaleString()}
            tone="success"
          />
          <KpiCard
            icon={UserPlus}
            label={t('analytics.identities.newToday')}
            value={personsLoading ? '—' : (personsSummary?.new_today ?? 0).toLocaleString()}
            tone="default"
          />
          <KpiCard
            icon={Repeat}
            label={t('analytics.identities.avgAppearances')}
            value={
              personsLoading
                ? '—'
                : (personsSummary?.avg_appearances ?? 0).toFixed(1)
            }
            tone="default"
          />
        </div>
      </div>

      {/* Live zone occupancy — known vs unknown headcount per zone */}
      <ZoneOccupancyPanel />

      {/* Per-person zone dwell — indoor geofencing (who is where, and how long) */}
      <ZoneDwellPanel />

      {/* Timeseries row */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <AlertsTimeseriesChart range={range} />
        <PeopleTimeseriesChart range={range} />
      </div>

      {/* Breakdown panel */}
      <AlertsBreakdownPanel range={range} />
    </div>
  );
}
