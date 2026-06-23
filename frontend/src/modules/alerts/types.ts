/**
 * Frontend mirror of the backend AlertRead schema. Field names match
 * exactly so we can deserialize directly without remapping.
 *
 * Source of truth: backend/app/modules/alerts/schemas.py:AlertRead
 */

export type AlertStatus = 'active' | 'acknowledged' | 'resolved';
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertRuleKind =
  | 'occupancy_max'
  | 'occupancy_min'
  | 'entry'
  | 'dwell';

export interface Alert {
  id: string;
  tenant_id: string;
  plan_id: string;
  zone_id: string;
  zone_name: string;
  rule_id: string;
  rule_kind: AlertRuleKind;
  rule_label: string | null;
  severity: AlertSeverity;
  condition_value: number;
  threshold: number;
  status: AlertStatus;
  fired_at: string; // ISO datetime
  acknowledged_at: string | null;
  acknowledged_by_user_id: string | null;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
  channels_attempted: string[];
  /** Free-form context. Shape varies by rule_kind. */
  extra: {
    cameras_in_zone?: { camera_id: string; count: number }[];
    reason?: string;
    [k: string]: unknown;
  };
}

export interface AlertListResponse {
  items: Alert[];
  total: number;
  limit: number;
  offset: number;
}

/** Server-side event names emitted via Socket.IO (see realtime_bridge.py). */
export const SOCKET_ALERT_FIRED = 'alert.fired';
export const SOCKET_ALERT_ACKED = 'alert.acknowledged';
export const SOCKET_ALERT_RESOLVED = 'alert.resolved';
