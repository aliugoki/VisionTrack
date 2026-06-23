import { Card } from '@/shared/components/Card';

interface KpiCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  tone?: 'default' | 'success' | 'warning' | 'danger';
}

const TONE_BG = {
  default: 'bg-muted',
  success: 'bg-emerald-500/10',
  warning: 'bg-amber-500/10',
  danger: 'bg-red-500/10',
};

const TONE_FG = {
  default: 'text-muted-foreground',
  success: 'text-emerald-600',
  warning: 'text-amber-600',
  danger: 'text-red-600',
};

/**
 * Single KPI tile for the analytics dashboard.
 * 4 of these sit in a row at the top of the page.
 */
export function KpiCard({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: KpiCardProps) {
  return (
    <Card className="flex items-center gap-3 p-3">
      <div className={`rounded-md p-2 ${TONE_BG[tone]}`}>
        <Icon className={`h-4 w-4 ${TONE_FG[tone]}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-muted-foreground">{label}</p>
        <p className="truncate text-lg font-semibold tabular-nums text-foreground">
          {value}
        </p>
      </div>
    </Card>
  );
}
