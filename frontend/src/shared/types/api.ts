/** Shared API DTOs — mirror backend/app/modules/* schemas. */

export type CameraStatus =
  | 'pending'
  | 'online'
  | 'offline'
  | 'error'
  | 'disabled';

export interface Site {
  id: string;
  tenant_id: string;
  name: string;
  address: string | null;
  timezone: string;
  is_active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  camera_count: number;
}

export interface SiteCreate {
  name: string;
  address?: string | null;
  timezone?: string;
}

/** A camera placement on a floor plan, surfaced on the camera list response. */
export interface CameraFloorPlanLocation {
  plan_id: string;
  plan_name: string;
  marker_id: string;
  marker_label: string | null;
}

export interface Camera {
  id: string;
  tenant_id: string;
  site_id: string;
  name: string;
  description: string | null;
  rtsp_url: string; // password-masked when read from server
  mediamtx_path: string;
  status: CameraStatus;
  is_recording: boolean;
  codec: string | null;
  last_seen_at: string | null;
  last_status_change_at: string | null;
  calibration: Record<string, unknown>;
  stream_config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  hls_url: string;
  /** Empty when the camera isn't placed on any floor plan. */
  floor_plan_locations: CameraFloorPlanLocation[];
}

export interface CameraCreate {
  name: string;
  description?: string | null;
  site_id: string;
  rtsp_url: string;
  is_recording?: boolean;
}

export interface CameraUpdate {
  name?: string;
  description?: string | null;
  rtsp_url?: string;
  is_recording?: boolean;
  calibration?: Record<string, unknown>;
}

export interface CameraDiscoveryResult {
  ip: string;
  port: number;
  manufacturer: string | null;
  model: string | null;
  serial: string | null;
  suggested_rtsp_url: string | null;
  xaddr: string;
}

export interface CameraDiscoveryRequest {
  username?: string;
  password?: string;
  timeout_seconds?: number;
}


/* -------------------------------------------------------------------------- */
/* Persons — cross-camera identities (P2.1+, populated by P2.5 matcher)       */
/* -------------------------------------------------------------------------- */

export interface Person {
  id: string;
  tenant_id: string;
  first_seen_at: string;
  last_seen_at: string;
  appearance_count: number;
  created_at: string;
}

export interface PersonTimelineEntry {
  track_id: string;
  camera_id: string;
  camera_name: string | null;
  started_at: string;
  ended_at: string | null;
  point_count: number;
}

export interface PersonDetail extends Person {
  timeline: PersonTimelineEntry[];
}
