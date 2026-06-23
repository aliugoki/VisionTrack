import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Bell,
  Check,
  CheckCheck,
  Filter,
  Info,
  Loader2,
  LogIn,
  TrendingDown,
  TrendingUp,
  Watch,
  X,
} from 'lucide-react';
import { Badge } from '@/shared/components/Badge';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { cn } from '@/shared/lib/cn';
import { useAuth } from '@/shared/hooks/useAuth';
import { AlertClipButton } from '@/modules/alerts/AlertClipButton';
import {
  useAcknowledgeAlert,
  useAlerts,
  useResolveAlert,
  type AlertFilters,
} from '@/modules/alerts/api';
import {
  useAlertsStream,
} from '@/modules/alerts/useAlertsStream';
import type {
  Alert,
  AlertRuleKind,
  AlertSeverity,
  AlertStatus,
} from '@/modules/alerts/types';
import { toast } from 'sonner';

const STATUS_TABS: { value: AlertStatus | 'all'; labelKey: string }[] = [
  { value: 'active', labelKey: 'alerts.filters.statuses.active' },
  { value: 'acknowledged', labelKey: 'alerts.filters.statuses.acknowledged' },
  { value: 'resolved', labelKey: 'alerts.filters.statuses.resolved' },
  { value: 'all', labelKey: 'alerts.filters.statuses.all' },
];

const SEVERITY_OPTIONS: { value: AlertSeverity | 'all'; labelKey: string }[] = [
  { value: 'all', labelKey: 'alerts.filters.severities.all' },
  { value: 'critical', labelKey: 'alerts.filters.severities.critical' },
  { value: 'warning', labelKey: 'alerts.filters.severities.warning' },
  { value: 'info', labelKey: 'alerts.filters.severities.info' },
];

export default function AlertsPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canAck = hasPermission('alert:acknowledge');
  const canResolve = hasPermission('alert:resolve');

  // Local filter state — kept simple, no URL sync (could be added later).
  const [statusTab, setStatusTab] = useState<AlertStatus | 'all'>('active');
  const [severity, setSeverity] = useState<AlertSeverity | 'all'>('all');

  // Build filter object for the API hook. statusTab='all' means no filter.
  const filters: AlertFilters = useMemo(() => {
    const f: AlertFilters = { limit: 100 };
    if (statusTab !== 'all') f.status = statusTab;
    if (severity !== 'all') f.severity = severity;
    return f;
  }, [statusTab, severity]);

  const { data, isLoading } = useAlerts(filters);
  const acknowledge = useAcknowledgeAlert();
  const resolve = useResolveAlert();

  // Mount the stream so this page also gets live updates while open.
  // Toasts are spawned in AppLayout (one global mount); here we just
  // want the cache to stay fresh.
  useAlertsStream({});

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <Bell className="h-6 w-6" />
            {t('alerts.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('alerts.subtitle')}
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card className="p-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Status tabs */}
          <div className="flex rounded-md border border-border bg-background p-0.5">
            {STATUS_TABS.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setStatusTab(s.value)}
                className={cn(
                  'rounded px-3 py-1 text-xs font-medium transition-colors',
                  statusTab === s.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {t(s.labelKey)}
              </button>
            ))}
          </div>

          {/* Severity dropdown */}
          <div className="flex items-center gap-1.5">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as AlertSeverity | 'all')}
              className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
            >
              {SEVERITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {t(o.labelKey)}
                </option>
              ))}
            </select>
          </div>

          {/* Live count badge */}
          <div className="ms-auto text-xs text-muted-foreground">
            {data
              ? t('alerts.counter', { shown: items.length, total: data.total })
              : null}
          </div>
        </div>
      </Card>

      {/* Body */}
      {isLoading ? (
        <Card className="flex items-center justify-center p-12">
          <Spinner size={24} />
        </Card>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
          <Bell className="h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">
            {t('alerts.empty.title')}
          </p>
          <p className="text-xs text-muted-foreground">
            {statusTab === 'active'
              ? t('alerts.empty.active')
              : t('alerts.empty.filtered')}
          </p>
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              canAck={canAck}
              canResolve={canResolve}
              busy={acknowledge.isPending || resolve.isPending}
              onAcknowledge={async () => {
                try {
                  await acknowledge.mutateAsync(alert.id);
                  toast.success(t('alerts.acknowledged'));
                } catch {
                  toast.error(t('alerts.actionFailed'));
                }
              }}
              onResolve={async () => {
                try {
                  await resolve.mutateAsync(alert.id);
                  toast.success(t('alerts.resolved'));
                } catch {
                  toast.error(t('alerts.actionFailed'));
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// -- AlertRow ----------------------------------------------------------------

const SEVERITY_BADGE_TONE: Record<AlertSeverity, 'primary' | 'warning' | 'danger'> = {
  info: 'primary',
  warning: 'warning',
  critical: 'danger',
};
const SEVERITY_ICON: Record<AlertSeverity, React.ComponentType<{ className?: string }>> = {
  info: Info,
  warning: AlertTriangle,
  critical: Bell,
};
const KIND_ICON: Record<AlertRuleKind, React.ComponentType<{ className?: string }>> = {
  occupancy_max: TrendingUp,
  occupancy_min: TrendingDown,
  entry: LogIn,
  dwell: Watch,
};
const STATUS_TONE: Record<AlertStatus, 'neutral' | 'primary' | 'success'> = {
  active: 'neutral',
  acknowledged: 'primary',
  resolved: 'success',
};

function AlertRow({
  alert,
  canAck,
  canResolve,
  busy,
  onAcknowledge,
  onResolve,
}: {
  alert: Alert;
  canAck: boolean;
  canResolve: boolean;
  busy: boolean;
  onAcknowledge: () => void;
  onResolve: () => void;
}) {
  const { t } = useTranslation();
  const SeverityIcon = SEVERITY_ICON[alert.severity];
  const KindIcon = KIND_ICON[alert.rule_kind];

  // Human-readable "X minutes ago". Tiny inline helper avoids a date-fns
  // dependency for this single use; precision is good enough for an
  // alert feed (we don't show seconds).
  const firedRelative = useMemo(() => timeAgo(alert.fired_at), [alert.fired_at]);

  // Human-readable rule description — same pattern as the rule list in
  // the editor sidebar, but tweaked for the alerts feed (past tense).
  const ruleSummary = (() => {
    if (alert.rule_kind === 'entry') {
      return t('alerts.summary.entry', { n: alert.threshold });
    }
    if (alert.rule_kind === 'occupancy_max') {
      return t('alerts.summary.occupancy_max', {
        count: Math.round(alert.condition_value),
        threshold: alert.threshold,
      });
    }
    if (alert.rule_kind === 'occupancy_min') {
      return t('alerts.summary.occupancy_min', {
        count: Math.round(alert.condition_value),
        threshold: alert.threshold,
      });
    }
    return t('alerts.summary.dwell', { s: alert.threshold });
  })();

  return (
    <Card
      className={cn(
        'flex items-stretch overflow-hidden',
        alert.status === 'active' &&
          alert.severity === 'critical' &&
          'border-danger/40'
      )}
    >
      {/* Left severity strip */}
      <div
        className={cn(
          'w-1 flex-shrink-0',
          alert.severity === 'info' && 'bg-sky-500',
          alert.severity === 'warning' && 'bg-amber-500',
          alert.severity === 'critical' && 'bg-red-500',
          alert.status === 'resolved' && 'opacity-40'
        )}
      />

      {/* Main content */}
      <div className="flex-1 p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-foreground">
                {alert.rule_label || alert.zone_name}
              </h3>
              <Badge tone={SEVERITY_BADGE_TONE[alert.severity]}>
                <SeverityIcon className="h-3 w-3" />
                {t(`alerts.filters.severities.${alert.severity}`)}
              </Badge>
              <Badge tone={STATUS_TONE[alert.status]}>
                {t(`alerts.filters.statuses.${alert.status}`)}
              </Badge>
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <KindIcon className="h-3 w-3" />
              <span className="font-medium text-foreground">
                {alert.zone_name}
              </span>
              <span>•</span>
              <span>{ruleSummary}</span>
              <span>•</span>
              <span title={alert.fired_at}>{firedRelative}</span>
            </p>
            {/* Audit footer for ack/resolve */}
            {(alert.acknowledged_at || alert.resolved_at) && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                {alert.resolved_at &&
                  t('alerts.audit.resolvedAt', { when: formatRelative(alert.resolved_at) })}
                {!alert.resolved_at && alert.acknowledged_at &&
                  t('alerts.audit.acknowledgedAt', { when: formatRelative(alert.acknowledged_at) })}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-shrink-0 items-center gap-1">
            <AlertClipButton alertId={alert.id} />
            {alert.status === 'active' && canAck && (
              <Button
                variant="outline"
                size="sm"
                onClick={onAcknowledge}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                {t('alerts.actions.acknowledge')}
              </Button>
            )}
            {alert.status !== 'resolved' && canResolve && (
              <Button
                size="sm"
                onClick={onResolve}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCheck className="h-3 w-3" />
                )}
                {t('alerts.actions.resolve')}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function formatRelative(iso: string): string {
  return timeAgo(iso);
}

/**
 * Compact "time ago" formatter. Returns "just now", "5m ago", "2h ago",
 * "3d ago", or the locale date for anything older than 7 days. Defensive
 * against malformed input — returns the raw string on parse failure.
 */
function timeAgo(iso: string): string {
  if (!iso) return '';
  const ts = new Date(iso).getTime();
  if (!Number.isFinite(ts)) return iso;
  const diffMs = Date.now() - ts;
  if (diffMs < 0) return 'in the future';
  const sec = Math.floor(diffMs / 1000);
  if (sec < 30) return 'just now';
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}
