/** Floor plan types — match backend FloorPlanRead schema. */

export type FloorPlanFormat = 'png' | 'jpg' | 'svg' | 'pdf';

/** Camera placement on a floor plan. Coordinates are fractional (0..1). */
export interface FloorPlanMarker {
  id: string;
  camera_id: string;
  x: number;
  y: number;
  label: string | null;
  /** FOV horizontal sweep in degrees. 1..360. Null = no cone shown. */
  cone_angle_deg: number | null;
  /** Cone radius as fraction of floor plan width. 0..1. Null = no cone shown. */
  cone_range: number | null;
  /** Rotation in degrees clockwise from east (positive x-axis). 0..359. */
  cone_rotation_deg: number | null;
}

/** Default cone values when operator first enables a cone for a marker. */
export const DEFAULT_CONE = {
  cone_angle_deg: 90,
  cone_range: 0.15,
  cone_rotation_deg: 0,
} as const;

export interface FloorPlan {
  id: string;
  tenant_id: string;
  site_id: string;
  uploaded_by_user_id: string | null;
  name: string;
  description: string | null;
  original_filename: string;
  original_content_type: string;
  original_size_bytes: number;
  format: FloorPlanFormat;
  width_px: number;
  height_px: number;
  markers: FloorPlanMarker[];
  zones: Zone[];
  created_at: string;
  updated_at: string;
}

export interface FloorPlanUpdate {
  name?: string;
  description?: string | null;
}

/** Accepted file extensions for upload (matches backend). */
export const ACCEPTED_EXTENSIONS = '.png,.jpg,.jpeg,.svg,.pdf';
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024; // 50 MB

// -- Zones (Step 5) ----------------------------------------------------------

/** One vertex of a zone polygon. Fractional (0..1) like marker coords. */
export interface ZonePoint {
  x: number;
  y: number;
}

export type ZoneRuleKind =
  | 'occupancy_max'
  | 'occupancy_min'
  | 'dwell'
  | 'entry';

export type ZoneRuleSeverity = 'info' | 'warning' | 'critical';
export type ZoneRuleChannel = 'in_app' | 'email' | 'whatsapp';
export type ScheduleMode = 'always' | 'scheduled';

export interface ZoneRuleSchedule {
  mode: ScheduleMode;
  start_time: string | null;
  end_time: string | null;
  days: number[]; // 0=Monday..6=Sunday
}

export interface ZoneRule {
  id: string;
  kind: ZoneRuleKind;
  threshold: number;
  hold_time_s: number;
  schedule: ZoneRuleSchedule;
  severity: ZoneRuleSeverity;
  channels: ZoneRuleChannel[];
  enabled: boolean;
  label: string | null;
}

export interface Zone {
  id: string;
  name: string;
  color: string;
  polygon: ZonePoint[];
  rules: ZoneRule[];
}

/**
 * Predefined zone color palette. We use a fixed set rather than a freeform
 * picker so zones stay visually distinguishable at a glance, and so each
 * color has a tested contrast against the floor plan background. Values
 * mirror Tailwind's "500" tones for the named hues, which look good as
 * translucent fills on both light and dark plans.
 */
export const ZONE_COLORS = [
  '#ef4444', // red-500
  '#f97316', // orange-500
  '#eab308', // yellow-500
  '#22c55e', // green-500
  '#14b8a6', // teal-500
  '#0ea5e9', // sky-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
] as const;

/** Default values when the operator creates a new zone (color picked from palette). */
export const DEFAULT_ZONE_COLOR = ZONE_COLORS[0];

/** Generate a unique id for a new zone or vertex (UUID v4 via crypto). */
export function newId(): string {
  // Prefer browser-native randomUUID; fallback for older browsers.
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // Fallback: RFC4122-ish from getRandomValues
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  a[6] = (a[6] & 0x0f) | 0x40;
  a[8] = (a[8] & 0x3f) | 0x80;
  const hex = Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('');
  return (
    hex.slice(0, 8) +
    '-' +
    hex.slice(8, 12) +
    '-' +
    hex.slice(12, 16) +
    '-' +
    hex.slice(16, 20) +
    '-' +
    hex.slice(20, 32)
  );
}
