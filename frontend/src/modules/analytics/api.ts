import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  AlertsBreakdownResponse,
  DateRange,
  PersonsSummary,
  OverviewKPIs,
  TimeseriesResponse,
} from '@/modules/analytics/types';

export const ANALYTICS_KEYS = {
  overview: (r: DateRange) =>
    ['analytics', 'overview', r.from, r.to] as const,
  alertsTimeseries: (r: DateRange) =>
    ['analytics', 'alerts-ts', r.from, r.to, r.bucket] as const,
  peopleTimeseries: (r: DateRange) =>
    ['analytics', 'people-ts', r.from, r.to, r.bucket] as const,
  personsSummary: () => ['analytics', 'persons-summary'] as const,
  alertsBreakdown: (r: DateRange) =>
    ['analytics', 'alerts-bk', r.from, r.to] as const,
};

const STALE_MS = 60_000; // 60s — analytics doesn't need real-time

export function useOverview(range: DateRange) {
  return useQuery({
    queryKey: ANALYTICS_KEYS.overview(range),
    staleTime: STALE_MS,
    queryFn: async () => {
      const { data } = await api.get<OverviewKPIs>('/analytics/overview', {
        params: { from: range.from, to: range.to },
      });
      return data;
    },
  });
}

export function useAlertsTimeseries(range: DateRange) {
  return useQuery({
    queryKey: ANALYTICS_KEYS.alertsTimeseries(range),
    staleTime: STALE_MS,
    queryFn: async () => {
      const { data } = await api.get<TimeseriesResponse>(
        '/analytics/alerts/timeseries',
        { params: { from: range.from, to: range.to, bucket: range.bucket } }
      );
      return data;
    },
  });
}

export function usePeopleTimeseries(range: DateRange) {
  return useQuery({
    queryKey: ANALYTICS_KEYS.peopleTimeseries(range),
    staleTime: STALE_MS,
    queryFn: async () => {
      const { data } = await api.get<TimeseriesResponse>(
        '/analytics/people/timeseries',
        { params: { from: range.from, to: range.to, bucket: range.bucket } }
      );
      return data;
    },
  });
}

export function useAlertsBreakdown(range: DateRange) {
  return useQuery({
    queryKey: ANALYTICS_KEYS.alertsBreakdown(range),
    staleTime: STALE_MS,
    queryFn: async () => {
      const { data } = await api.get<AlertsBreakdownResponse>(
        '/analytics/alerts/breakdown',
        { params: { from: range.from, to: range.to } }
      );
      return data;
    },
  });
}


export function usePersonsSummary() {
  return useQuery({
    queryKey: ANALYTICS_KEYS.personsSummary(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data } = await api.get<PersonsSummary>('/analytics/persons/summary');
      return data;
    },
  });
}
