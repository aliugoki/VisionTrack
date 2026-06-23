import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  Alert,
  AlertListResponse,
  AlertSeverity,
  AlertStatus,
} from '@/modules/alerts/types';

// React Query keys. The "list" key is parameterized by filters so each
// filter combination has its own cache slot — switching filters won't
// reuse a stale result.
export const ALERTS_KEYS = {
  all: ['alerts'] as const,
  list: (filters: AlertFilters) => ['alerts', 'list', filters] as const,
  detail: (id: string) => ['alerts', 'detail', id] as const,
} as const;

export interface AlertFilters {
  status?: AlertStatus;
  severity?: AlertSeverity;
  zone_id?: string;
  limit?: number;
  offset?: number;
}

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: ALERTS_KEYS.list(filters),
    queryFn: async () => {
      // Build query params, omitting undefined values so the URL is
      // canonical and the backend doesn't see noise.
      const params: Record<string, string | number> = {};
      if (filters.status) params.status = filters.status;
      if (filters.severity) params.severity = filters.severity;
      if (filters.zone_id) params.zone_id = filters.zone_id;
      params.limit = filters.limit ?? 50;
      params.offset = filters.offset ?? 0;
      const { data } = await api.get<AlertListResponse>('/alerts', { params });
      return data;
    },
    // Keep recent alerts feed visibly responsive. With Socket.IO live
    // updates these are usually fresh, but the staleTime mirrors what
    // the operator perceives as "real-time enough."
    staleTime: 10_000,
  });
}

export function useAlert(id: string | null | undefined) {
  return useQuery({
    queryKey: ALERTS_KEYS.detail(id || ''),
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<Alert>(`/alerts/${id}`);
      return data;
    },
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post<Alert>(`/alerts/${id}/acknowledge`);
      return data;
    },
    onSuccess: () => {
      // Invalidate ALL alerts caches — any filter combination might
      // include or exclude the just-updated row. Cheap enough at our
      // volume to do unconditionally.
      qc.invalidateQueries({ queryKey: ALERTS_KEYS.all });
    },
  });
}

export function useResolveAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post<Alert>(`/alerts/${id}/resolve`);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ALERTS_KEYS.all });
    },
  });
}
