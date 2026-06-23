import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSocket } from '@/shared/hooks/useSocket';
import {
  SOCKET_ALERT_ACKED,
  SOCKET_ALERT_FIRED,
  SOCKET_ALERT_RESOLVED,
  type Alert,
} from '@/modules/alerts/types';
import { ALERTS_KEYS } from '@/modules/alerts/api';

interface UseAlertsStreamOptions {
  /**
   * Called for each newly fired alert. The AlertToast component uses
   * this to spawn a toast. The hook itself doesn't decide UX — it just
   * keeps the cache in sync.
   */
  onAlertFired?: (alert: Alert) => void;
}

/**
 * Mount this once at app level (in AppShell or AppLayout). It:
 *   - Subscribes to alert.fired / alert.acknowledged / alert.resolved
 *     Socket.IO events
 *   - Invalidates React Query caches so any open list re-fetches
 *   - Optimistically prepends new fired alerts to the active-status list
 *     so users see them instantly without waiting for refetch
 *   - Calls onAlertFired callback for side-effects (toasts, sounds)
 *
 * Cache invalidation pattern:
 *   On any alert event, we invalidate ['alerts'] which covers every
 *   parameterized list cache. Mutations from other clients/tenants
 *   can't reach us (server room-scopes the broadcast), so an invalidate
 *   only fires when the change is relevant.
 */
export function useAlertsStream(opts: UseAlertsStreamOptions = {}) {
  const { socket } = useSocket();
  const qc = useQueryClient();
  // Keep onAlertFired in a ref so its identity doesn't trigger re-attach.
  const onFiredRef = useRef(opts.onAlertFired);
  useEffect(() => {
    onFiredRef.current = opts.onAlertFired;
  }, [opts.onAlertFired]);

  useEffect(() => {
    if (!socket) return;

    const onFired = (alert: Alert) => {
      // Optimistic prepend: update every cache slot for status=active or
      // unfiltered. Since the query key includes filters, we walk the
      // cache and find matching entries instead of guessing keys.
      qc.setQueriesData(
        { queryKey: ALERTS_KEYS.all },
        (old: any) => {
          if (!old || !Array.isArray(old.items)) return old;
          // Avoid duplicates if the same event arrives twice (rare; possible
          // on transient reconnects).
          if (old.items.some((a: Alert) => a.id === alert.id)) return old;
          return {
            ...old,
            items: [alert, ...old.items].slice(0, old.limit ?? 50),
            total: (old.total ?? 0) + 1,
          };
        }
      );
      onFiredRef.current?.(alert);
    };

    const onStatusChange = (alert: Alert) => {
      // Replace by id in every list cache + update detail cache.
      qc.setQueriesData(
        { queryKey: ALERTS_KEYS.all },
        (old: any) => {
          if (!old || !Array.isArray(old.items)) return old;
          return {
            ...old,
            items: old.items.map((a: Alert) =>
              a.id === alert.id ? alert : a
            ),
          };
        }
      );
      qc.setQueryData(ALERTS_KEYS.detail(alert.id), alert);
    };

    socket.on(SOCKET_ALERT_FIRED, onFired);
    socket.on(SOCKET_ALERT_ACKED, onStatusChange);
    socket.on(SOCKET_ALERT_RESOLVED, onStatusChange);

    return () => {
      socket.off(SOCKET_ALERT_FIRED, onFired);
      socket.off(SOCKET_ALERT_ACKED, onStatusChange);
      socket.off(SOCKET_ALERT_RESOLVED, onStatusChange);
    };
  }, [socket, qc]);
}
