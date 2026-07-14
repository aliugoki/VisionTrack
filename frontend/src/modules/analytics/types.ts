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


export interface KnownPerson {
  emp_id: string;
  name: string | null;
}

export interface ZoneOccupancy {
  floor_plan_id: string;
  floor_plan_name: string | null;
  zone_id: string;
  zone_name: string;
  camera_ids: string[];
  total: number;
  known: number;
  unknown: number;
  known_people: KnownPerson[];
}

export interface ZoneOccupancyResponse {
  as_of: string;
  active_window_sec: number;
  zones: ZoneOccupancy[];
}

export interface ZoneDwellRow {
  emp_id: string;
  name: string | null;
  floor_plan_id: string;
  floor_plan_name: string | null;
  zone_id: string;
  zone_name: string;
  seconds: number;
  sessions: number;
  first_seen: string; // ISO datetime
  last_seen: string; // ISO datetime
  present: boolean; // still in the zone right now
}

export interface ZoneDwellResponse {
  as_of: string;
  from: string; // window lower bound (inclusive)
  to: string; // window upper bound (exclusive)
  active_window_sec: number;
  rows: ZoneDwellRow[];
}

export interface TimelineSegment {
  zone_id: string;
  zone_name: string;
  floor_plan_id: string;
  floor_plan_name: string | null;
  start: string; // ISO datetime
  end: string; // ISO datetime
  seconds: number;
  sessions: number;
  present: boolean;
}

export interface PersonTimelineResponse {
  emp_id: string;
  name: string | null;
  as_of: string;
  from: string;
  to: string;
  total_seconds: number;
  segments: TimelineSegment[];
}

export interface AttendanceRow {
  emp_id: string;
  name: string | null;
  arrival: string; // ISO datetime
  departure: string; // ISO datetime
  span_seconds: number; // wall-clock arrival -> departure
  tracked_seconds: number; // total time inside zones
  zones_count: number;
  present: boolean;
}

export interface AttendanceResponse {
  as_of: string;
  from: string;
  to: string;
  rows: AttendanceRow[];
}

export interface ZoneRollupRow {
  zone_id: string;
  zone_name: string;
  floor_plan_id: string | null;
  floor_plan_name: string | null;
  total_seconds: number;
  people_count: number;
  avg_seconds: number;
  present_count: number;
}

export interface ZoneRollupResponse {
  as_of: string;
  from: string;
  to: string;
  rows: ZoneRollupRow[];
}
