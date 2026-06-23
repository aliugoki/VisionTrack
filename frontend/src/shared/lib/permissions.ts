/**
 * Permission keys — kept in sync with backend/app/core/permissions.py.
 *
 * The full catalog (with labels and groups) is fetched at runtime from
 * GET /api/v1/roles/permissions, but the keys themselves need to be
 * available as constants for compile-time permission checks in the UI.
 */

// Tenants
export const TENANT_READ = 'tenant:read';
export const TENANT_UPDATE = 'tenant:update';

// Users
export const USER_READ = 'user:read';
export const USER_CREATE = 'user:create';
export const USER_UPDATE = 'user:update';
export const USER_DELETE = 'user:delete';
export const USER_INVITE = 'user:invite';

// Roles
export const ROLE_READ = 'role:read';
export const ROLE_CREATE = 'role:create';
export const ROLE_UPDATE = 'role:update';
export const ROLE_DELETE = 'role:delete';
export const ROLE_ASSIGN = 'role:assign';

// Sites
export const SITE_READ = 'site:read';
export const SITE_CREATE = 'site:create';
export const SITE_UPDATE = 'site:update';
export const SITE_DELETE = 'site:delete';

// Cameras
export const CAMERA_READ = 'camera:read';
export const CAMERA_CREATE = 'camera:create';
export const CAMERA_UPDATE = 'camera:update';
export const CAMERA_DELETE = 'camera:delete';
export const CAMERA_CALIBRATE = 'camera:calibrate';
export const CAMERA_STREAM_VIEW = 'camera:stream_view';

// Zones
export const ZONE_READ = 'zone:read';
export const ZONE_CREATE = 'zone:create';
export const ZONE_UPDATE = 'zone:update';
export const ZONE_DELETE = 'zone:delete';

// Employees
export const EMPLOYEE_READ = 'employee:read';
export const EMPLOYEE_CREATE = 'employee:create';
export const EMPLOYEE_UPDATE = 'employee:update';
export const EMPLOYEE_DELETE = 'employee:delete';
export const EMPLOYEE_ENROLL = 'employee:enroll';

// Tracks
export const TRACK_READ = 'track:read';
export const TRACK_REPLAY = 'track:replay';

// Events
export const EVENT_READ = 'event:read';
export const EVENT_EXPORT = 'event:export';

// Alerts
export const ALERT_READ = 'alert:read';
export const ALERT_ACKNOWLEDGE = 'alert:acknowledge';
export const ALERT_RESOLVE = 'alert:resolve';
export const ALERT_ASSIGN = 'alert:assign';
export const ALERT_RULE_READ = 'alert_rule:read';
export const ALERT_RULE_CREATE = 'alert_rule:create';
export const ALERT_RULE_UPDATE = 'alert_rule:update';
export const ALERT_RULE_DELETE = 'alert_rule:delete';

// Recordings
export const RECORDING_READ = 'recording:read';
export const RECORDING_EXPORT = 'recording:export';
export const RECORDING_DELETE = 'recording:delete';

// Analytics
export const ANALYTICS_READ = 'analytics:read';
export const REPORT_GENERATE = 'report:generate';
export const REPORT_EXPORT = 'report:export';

// Safety / Evacuation (Phase 2.5 — keys reserved now)
export const EVACUATION_TRIGGER = 'evacuation:trigger';
export const EVACUATION_READ = 'evacuation:read';
export const EVACUATION_CONFIRM_SAFE = 'evacuation:confirm_safe';
export const EVACUATION_GENERATE_REPORT = 'evacuation:generate_report';
export const MUSTER_POINT_MANAGE = 'muster_point:manage';
