/**
 * Mirror of backend analytics schemas.
 * Source: backend/app/modules/analytics/schemas.py
 */

export interface OverviewKPIs {
  alerts_total: number;
  alerts_active: number;
  alerts_critical: number;
  distinct_zones_with_alerts: number;
  distinct_persons_tracked: number;
  recordings_count: number;
  recordings_size_bytes: number;
}

export interface TimeseriesPoint {
  bucket_start: string; // ISO datetime
  count: number;
}

export interface TimeseriesResponse {
  bucket: 'hour' | 'day';
  points: TimeseriesPoint[];
}

export interface BreakdownItem {
  label: string;
  count: number;
}

export interface AlertsBreakdownResponse {
  by_severity: BreakdownItem[];
  by_zone: BreakdownItem[];
  by_rule: BreakdownItem[];
}

/** Half-open date range [from, to) — both as ISO datetime strings. */
export interface DateRange {
  from: string;
  to: string;
  bucket: 'hour' | 'day';
}


export interface PersonsSummary {
  total_identities: number;
  active_last_24h: number;
  new_today: number;
  avg_appearances: number;
}
