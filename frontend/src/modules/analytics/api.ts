import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  AlertsBreakdownResponse,
  AttendanceResponse,
  DateRange,
  PersonsSummary,
  OverviewKPIs,
  PersonTimelineResponse,
  TimeseriesResponse,
  OccupancyHeatmapResponse,
  ZoneDwellResponse,
  ZoneOccupancyResponse,
  ZoneRollupResponse,
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

// Live zone occupancy — refreshes every 5s (unlike the 60s analytics panels).
export function useZoneOccupancy(windowSec = 60) {
  return useQuery({
    queryKey: ['analytics', 'zone-occupancy', windowSec] as const,
    refetchInterval: 5_000,
    queryFn: async () => {
      const { data } = await api.get<ZoneOccupancyResponse>(
        '/analytics/zones/occupancy',
        { params: { window: windowSec } },
      );
      return data;
    },
  });
}

// Per-person zone dwell ("indoor geofencing") — who was in which zone and for
// how long. Defaults to today (server-side). Refreshes every 15s so the
// "here now" flags and running totals stay current without hammering the DB.
export function useZoneDwell(params?: {
  from?: string;
  to?: string;
  minSeconds?: number;
}) {
  return useQuery({
    queryKey: [
      'analytics',
      'zone-dwell',
      params?.from ?? null,
      params?.to ?? null,
      params?.minSeconds ?? 0,
    ] as const,
    refetchInterval: 15_000,
    queryFn: async () => {
      const { data } = await api.get<ZoneDwellResponse>('/analytics/zones/dwell', {
        params: {
          from: params?.from,
          to: params?.to,
          min_seconds: params?.minSeconds,
        },
      });
      return data;
    },
  });
}

// ---- CSV export (authenticated blob download) ----------------------------- //

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function todayStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

export interface DwellFilters {
  from?: string;
  to?: string;
  minSeconds?: number;
  empId?: string;
  zoneId?: string;
}

/** Download per-employee zone dwell as CSV, honouring the given filters. */
export async function downloadDwellCsv(filters: DwellFilters = {}): Promise<void> {
  const { data } = await api.get<Blob>('/analytics/zones/dwell.csv', {
    responseType: 'blob',
    params: {
      from: filters.from,
      to: filters.to,
      min_seconds: filters.minSeconds,
      emp_id: filters.empId,
      zone_id: filters.zoneId,
    },
  });
  triggerDownload(data, `zone-dwell-${todayStamp()}.csv`);
}

/** Download one employee's zone-visit timeline for today as CSV. */
export async function downloadTimelineCsv(
  empId: string,
  name?: string | null,
): Promise<void> {
  const { data } = await api.get<Blob>(
    `/analytics/persons/${encodeURIComponent(empId)}/timeline.csv`,
    { responseType: 'blob' },
  );
  const who = (name || empId).replace(/[^\w-]+/g, '_').slice(0, 40);
  triggerDownload(data, `timeline-${who}-${todayStamp()}.csv`);
}

/** Per-employee attendance (arrival / departure / on-site span / tracked). */
export function useAttendance(filters: DwellFilters = {}) {
  return useQuery({
    queryKey: [
      'analytics',
      'attendance',
      filters.from ?? null,
      filters.to ?? null,
      filters.minSeconds ?? 0,
      filters.empId ?? null,
      filters.zoneId ?? null,
    ] as const,
    queryFn: async () => {
      const { data } = await api.get<AttendanceResponse>('/analytics/attendance', {
        params: {
          from: filters.from,
          to: filters.to,
          min_seconds: filters.minSeconds,
          emp_id: filters.empId,
          zone_id: filters.zoneId,
        },
      });
      return data;
    },
  });
}

/** Download per-employee attendance as CSV, honouring the given filters. */
export async function downloadAttendanceCsv(filters: DwellFilters = {}): Promise<void> {
  const { data } = await api.get<Blob>('/analytics/attendance.csv', {
    responseType: 'blob',
    params: {
      from: filters.from,
      to: filters.to,
      min_seconds: filters.minSeconds,
      emp_id: filters.empId,
      zone_id: filters.zoneId,
    },
  });
  triggerDownload(data, `attendance-${todayStamp()}.csv`);
}

/** Per-zone rollup (total person-time, distinct people, avg, present). */
export function useZoneRollup(filters: DwellFilters = {}) {
  return useQuery({
    queryKey: [
      'analytics',
      'zone-rollup',
      filters.from ?? null,
      filters.to ?? null,
      filters.minSeconds ?? 0,
      filters.empId ?? null,
      filters.zoneId ?? null,
    ] as const,
    queryFn: async () => {
      const { data } = await api.get<ZoneRollupResponse>('/analytics/zones/rollup', {
        params: {
          from: filters.from,
          to: filters.to,
          min_seconds: filters.minSeconds,
          emp_id: filters.empId,
          zone_id: filters.zoneId,
        },
      });
      return data;
    },
  });
}

/** Download the per-zone rollup as CSV, honouring the given filters. */
export async function downloadZoneRollupCsv(filters: DwellFilters = {}): Promise<void> {
  const { data } = await api.get<Blob>('/analytics/zones/rollup.csv', {
    responseType: 'blob',
    params: {
      from: filters.from,
      to: filters.to,
      min_seconds: filters.minSeconds,
      emp_id: filters.empId,
      zone_id: filters.zoneId,
    },
  });
  triggerDownload(data, `zone-rollup-${todayStamp()}.csv`);
}

/** Hour-of-day occupancy heatmap (per zone, person-time + people per hour). */
export function useOccupancyHeatmap(filters: DwellFilters = {}) {
  return useQuery({
    queryKey: [
      'analytics',
      'heatmap',
      filters.from ?? null,
      filters.to ?? null,
      filters.empId ?? null,
      filters.zoneId ?? null,
    ] as const,
    queryFn: async () => {
      const { data } = await api.get<OccupancyHeatmapResponse>('/analytics/zones/heatmap', {
        params: {
          from: filters.from,
          to: filters.to,
          emp_id: filters.empId,
          zone_id: filters.zoneId,
        },
      });
      return data;
    },
  });
}

/** Download the hour-of-day occupancy heatmap as CSV. */
export async function downloadHeatmapCsv(filters: DwellFilters = {}): Promise<void> {
  const { data } = await api.get<Blob>('/analytics/zones/heatmap.csv', {
    responseType: 'blob',
    params: {
      from: filters.from,
      to: filters.to,
      emp_id: filters.empId,
      zone_id: filters.zoneId,
    },
  });
  triggerDownload(data, `occupancy-heatmap-${todayStamp()}.csv`);
}

// "Where was X today" — one employee's chronological zone-visit timeline.
// Disabled until an employee is selected. Refreshes every 15s so an in-progress
// visit keeps growing.
export function usePersonTimeline(
  empId: string | null,
  params?: { from?: string; to?: string; mergeGap?: number },
) {
  return useQuery({
    queryKey: [
      'analytics',
      'person-timeline',
      empId,
      params?.from ?? null,
      params?.to ?? null,
      params?.mergeGap ?? 60,
    ] as const,
    enabled: !!empId,
    refetchInterval: 15_000,
    queryFn: async () => {
      const { data } = await api.get<PersonTimelineResponse>(
        `/analytics/persons/${encodeURIComponent(empId as string)}/timeline`,
        {
          params: {
            from: params?.from,
            to: params?.to,
            merge_gap: params?.mergeGap,
          },
        },
      );
      return data;
    },
  });
}
