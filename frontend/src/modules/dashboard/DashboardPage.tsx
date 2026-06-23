import { useTranslation } from 'react-i18next';
import { Video, Activity, BellRing, ScanEye } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { cn } from '@/shared/lib/cn';

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  tone?: 'default' | 'primary' | 'warning' | 'danger';
}

function StatCard({ label, value, hint, icon: Icon, tone = 'default' }: StatCardProps) {
  const toneStyles = {
    default: 'text-muted-foreground bg-muted',
    primary: 'text-primary bg-primary/10',
    warning: 'text-warning bg-warning/10',
    danger: 'text-danger bg-danger/10',
  }[tone];

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 font-mono text-3xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className={cn('rounded-md p-2.5', toneStyles)}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-live-pulse rounded-full bg-success opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t('dashboard.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('dashboard.subtitle')}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t('dashboard.stats.camerasOnline')}
          value="0 / 0"
          icon={Video}
          tone="default"
        />
        <StatCard
          label={t('dashboard.stats.activeTracks')}
          value="0"
          icon={Activity}
          tone="primary"
        />
        <StatCard
          label={t('dashboard.stats.openAlerts')}
          value="0"
          icon={BellRing}
          tone="warning"
        />
        <StatCard
          label={t('dashboard.stats.eventsToday')}
          value="0"
          icon={ScanEye}
          tone="default"
        />
      </div>

      <Card className="p-12 text-center">
        <p className="text-sm text-muted-foreground">
          Once you connect your first camera in{' '}
          <span className="font-medium text-foreground">{t('nav.cameras')}</span>,
          live tracks and events will appear here.
        </p>
      </Card>
    </div>
  );
}
