import { useTranslation } from 'react-i18next';
import { Calendar } from 'lucide-react';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { cn } from '@/shared/lib/cn';
import type { DateRange } from '@/modules/analytics/types';

interface DateRangePickerProps {
  value: DateRange;
  onChange: (next: DateRange) => void;
}

type Preset = '24h' | '7d' | '30d';

/**
 * Date range picker for the analytics dashboard.
 *
 * Three preset buttons cover 95% of operator use-cases:
 *   - Last 24 hours (hour buckets)
 *   - Last 7 days (day buckets) — default
 *   - Last 30 days (day buckets)
 *
 * Bucket size auto-derives from the range. We don't expose a bucket
 * selector — the right resolution is determined by span. Hour buckets
 * for 30 days would produce 720 points (unreadable).
 *
 * Custom date input is intentionally OUT OF SCOPE for now. The three
 * presets handle the common cases; "from {date} to {date}" requires
 * a more involved UI that's better as a follow-on.
 */
export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const { t } = useTranslation();

  const applyPreset = (p: Preset) => {
    const now = new Date();
    let from: Date;
    let bucket: 'hour' | 'day';
    switch (p) {
      case '24h':
        from = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        bucket = 'hour';
        break;
      case '7d':
        from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        bucket = 'day';
        break;
      case '30d':
        from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        bucket = 'day';
        break;
    }
    onChange({
      from: from.toISOString(),
      to: now.toISOString(),
      bucket,
    });
  };

  // Determine which preset is currently active based on the value.
  // Active = span matches preset within a small tolerance.
  const activePreset = inferPreset(value);

  return (
    <Card className="p-2">
      <div className="flex items-center gap-2">
        <Calendar className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <PresetButton
          active={activePreset === '24h'}
          onClick={() => applyPreset('24h')}
        >
          {t('analytics.range.last24h')}
        </PresetButton>
        <PresetButton
          active={activePreset === '7d'}
          onClick={() => applyPreset('7d')}
        >
          {t('analytics.range.last7d')}
        </PresetButton>
        <PresetButton
          active={activePreset === '30d'}
          onClick={() => applyPreset('30d')}
        >
          {t('analytics.range.last30d')}
        </PresetButton>
      </div>
    </Card>
  );
}

function PresetButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs font-medium transition',
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
      )}
    >
      {children}
    </button>
  );
}

function inferPreset(range: DateRange): Preset | null {
  const from = new Date(range.from).getTime();
  const to = new Date(range.to).getTime();
  const hours = (to - from) / (1000 * 60 * 60);
  // Loose match (±1 hour) to accommodate sub-second drift between
  // when onChange fires and when this re-runs
  if (Math.abs(hours - 24) < 1) return '24h';
  if (Math.abs(hours - 24 * 7) < 24) return '7d';
  if (Math.abs(hours - 24 * 30) < 24) return '30d';
  return null;
}
