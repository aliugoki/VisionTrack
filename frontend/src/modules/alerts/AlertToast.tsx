import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAlertsStream } from '@/modules/alerts/useAlertsStream';
import { useAuth } from '@/shared/hooks/useAuth';
import type { Alert } from '@/modules/alerts/types';

/**
 * Toast spawner for live alerts.
 *
 * Mounted once at the app shell level. Subscribes to the alert.fired
 * Socket.IO event via useAlertsStream and spawns a sonner toast for
 * each new alert. Also keeps the alerts cache fresh as a side-effect.
 *
 * Toast styling per severity:
 *   critical → sonner's `error` (red) with longer duration
 *   warning  → sonner's `warning` (amber)
 *   info     → sonner's `info` (sky)
 *
 * Toasts are dismissible and link to /alerts on click. We dedupe by
 * alert id (sonner's `id` field) so a brief socket reconnect doesn't
 * spawn the same toast twice.
 */
export function AlertToastMounter() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();

  // Only spawn the stream subscription if the user can actually see
  // alerts. This avoids "phantom toasts" if a permission-less user
  // somehow joined a tenant room with active alerts.
  const enabled = hasPermission('alert:read');

  // The stream itself handles cache updates; we pass a callback to
  // additionally fire toasts.
  useAlertsStream({
    onAlertFired: enabled ? (alert) => fireToast(alert, t, navigate) : undefined,
  });

  // We mount nothing — toasts are spawned imperatively by sonner.
  return null;
}

function fireToast(
  alert: Alert,
  t: (k: string, opts?: any) => string,
  navigate: (path: string) => void
) {
  const title = alert.rule_label || alert.zone_name;
  const subtitle =
    alert.rule_kind === 'entry'
      ? t('alerts.toast.entry', { zone: alert.zone_name })
      : alert.rule_kind === 'occupancy_max'
      ? t('alerts.toast.occupancy_max', {
          zone: alert.zone_name,
          count: Math.round(alert.condition_value),
          threshold: alert.threshold,
        })
      : alert.rule_kind === 'occupancy_min'
      ? t('alerts.toast.occupancy_min', {
          zone: alert.zone_name,
          count: Math.round(alert.condition_value),
          threshold: alert.threshold,
        })
      : t('alerts.toast.generic', { zone: alert.zone_name });

  const handler = () => navigate('/alerts');

  const opts = {
    id: alert.id, // dedupe across reconnects
    description: subtitle,
    duration:
      alert.severity === 'critical'
        ? 15_000
        : alert.severity === 'warning'
        ? 8_000
        : 5_000,
    action: {
      label: t('alerts.toast.view'),
      onClick: handler,
    },
  };

  if (alert.severity === 'critical') {
    toast.error(title, opts);
  } else if (alert.severity === 'warning') {
    toast.warning(title, opts);
  } else {
    toast.info(title, opts);
  }
}
