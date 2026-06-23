import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Bell } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import { useAlerts } from '@/modules/alerts/api';
import { useAuth } from '@/shared/hooks/useAuth';

/**
 * Persistent banner shown at the top of the app whenever there are
 * unacknowledged alerts. Clicks navigate to /alerts.
 *
 * Hides itself entirely when:
 *   - User lacks alert:read (no count to show)
 *   - There are zero active alerts (clean state)
 *
 * Visual hierarchy:
 *   - Any active alert: amber background
 *   - Any active CRITICAL alert: red background + subtle pulse
 *
 * Performance:
 *   We use the same React Query cache as the /alerts page (filtered to
 *   status=active). So mounting this once globally costs one query that
 *   the live socket stream keeps fresh — no separate polling.
 */
export function AlertBanner() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const enabled = hasPermission('alert:read');

  // Query the active alerts (filtered server-side). The list page uses
  // the same key when status=active and limit=100, so this is a cache hit
  // most of the time.
  const { data } = useAlerts(enabled ? { status: 'active', limit: 100 } : {});

  if (!enabled || !data || data.total === 0) return null;

  const items = data.items;
  const hasCritical = items.some((a) => a.severity === 'critical');
  const tone = hasCritical
    ? 'bg-danger/15 text-danger border-danger/30'
    : 'bg-warning/15 text-warning-foreground border-warning/40';

  return (
    <Link
      to="/alerts"
      className={cn(
        'flex items-center justify-center gap-2 border-b px-4 py-1.5 text-xs font-medium transition-colors hover:brightness-95',
        tone
      )}
    >
      {hasCritical ? (
        <AlertTriangle className={cn('h-3.5 w-3.5', 'animate-pulse')} />
      ) : (
        <Bell className="h-3.5 w-3.5" />
      )}
      <span>
        {hasCritical
          ? t('alerts.banner.critical', { count: data.total })
          : t('alerts.banner.active', { count: data.total })}
      </span>
      <span className="underline-offset-2 group-hover:underline">
        {t('alerts.banner.cta')}
      </span>
    </Link>
  );
}
