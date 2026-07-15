/**
 * Mirror of backend TenantRead + TenantUpdate schemas.
 * Keep in sync with backend/app/modules/tenants/schemas.py
 */

export interface Tenant {
  id: string;
  name: string;
  subdomain: string;
  plan: string;
  is_active: boolean;
  timezone: string;
  recording_retention_days: number;
  use_deepstream: boolean;
  facetrack_feed_enabled: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TenantUpdate {
  name?: string;
  timezone?: string;
  settings?: Record<string, unknown>;
  is_active?: boolean;
  recording_retention_days?: number;
  use_deepstream?: boolean;
  facetrack_feed_enabled?: boolean;
}
