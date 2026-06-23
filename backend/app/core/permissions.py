"""Permission registry.

Every protected action in VisionTrack is named here as a string in the form
`resource:action`. Roles are stored in the database as JSONB arrays of these
strings. To add a new permission anywhere in the system:

  1. Add the constant here.
  2. Add it to PERMISSION_CATALOG with a human-readable description.
  3. Use `RequirePermission("...")` on the route.

The catalog is exposed via an API endpoint so the frontend can render
the permission matrix in the role editor UI.
"""

from typing import Final


# -- Tenants -------------------------------------------------------------------
TENANT_READ: Final = "tenant:read"
TENANT_UPDATE: Final = "tenant:update"

# -- Users ---------------------------------------------------------------------
USER_READ: Final = "user:read"
USER_CREATE: Final = "user:create"
USER_UPDATE: Final = "user:update"
USER_DELETE: Final = "user:delete"
USER_INVITE: Final = "user:invite"

# -- Roles ---------------------------------------------------------------------
ROLE_READ: Final = "role:read"
ROLE_CREATE: Final = "role:create"
ROLE_UPDATE: Final = "role:update"
ROLE_DELETE: Final = "role:delete"
ROLE_ASSIGN: Final = "role:assign"

# -- Sites ---------------------------------------------------------------------
SITE_READ: Final = "site:read"
SITE_CREATE: Final = "site:create"
SITE_UPDATE: Final = "site:update"
SITE_DELETE: Final = "site:delete"

# -- Cameras -------------------------------------------------------------------
CAMERA_READ: Final = "camera:read"
CAMERA_CREATE: Final = "camera:create"
CAMERA_UPDATE: Final = "camera:update"
CAMERA_DELETE: Final = "camera:delete"
CAMERA_CALIBRATE: Final = "camera:calibrate"
CAMERA_STREAM_VIEW: Final = "camera:stream_view"

# -- Zones ---------------------------------------------------------------------
ZONE_READ: Final = "zone:read"
ZONE_CREATE: Final = "zone:create"
ZONE_UPDATE: Final = "zone:update"
ZONE_DELETE: Final = "zone:delete"

# -- Employees -----------------------------------------------------------------
EMPLOYEE_READ: Final = "employee:read"
EMPLOYEE_CREATE: Final = "employee:create"
EMPLOYEE_UPDATE: Final = "employee:update"
EMPLOYEE_DELETE: Final = "employee:delete"
EMPLOYEE_ENROLL: Final = "employee:enroll"

# -- Tracks --------------------------------------------------------------------
TRACK_READ: Final = "track:read"
TRACK_REPLAY: Final = "track:replay"

# -- Live Wall -----------------------------------------------------------------
# Viewing the live wall reuses CAMERA_STREAM_VIEW; this permission gates
# creating, editing, and deleting wall presets (shared across the tenant).
LIVE_WALL_MANAGE_PRESETS: Final = "live_wall:manage_presets"

# -- Floor Plans ---------------------------------------------------------------
# Read = view list + view image. Create = upload a new floor plan. Update =
# rename / re-describe. Delete = remove the plan (cascades MinIO files).
FLOOR_PLAN_READ: Final = "floor_plan:read"
FLOOR_PLAN_CREATE: Final = "floor_plan:create"
FLOOR_PLAN_UPDATE: Final = "floor_plan:update"
FLOOR_PLAN_DELETE: Final = "floor_plan:delete"

# -- Events --------------------------------------------------------------------
EVENT_READ: Final = "event:read"
EVENT_EXPORT: Final = "event:export"

# -- Alerts --------------------------------------------------------------------
ALERT_READ: Final = "alert:read"
ALERT_ACKNOWLEDGE: Final = "alert:acknowledge"
ALERT_RESOLVE: Final = "alert:resolve"
ALERT_ASSIGN: Final = "alert:assign"
ALERT_RULE_READ: Final = "alert_rule:read"
ALERT_RULE_CREATE: Final = "alert_rule:create"
ALERT_RULE_UPDATE: Final = "alert_rule:update"
ALERT_RULE_DELETE: Final = "alert_rule:delete"

# -- Recordings ----------------------------------------------------------------
RECORDING_READ: Final = "recording:read"
RECORDING_EXPORT: Final = "recording:export"
RECORDING_DELETE: Final = "recording:delete"

# -- Analytics & Reports -------------------------------------------------------
ANALYTICS_READ: Final = "analytics:read"
REPORT_GENERATE: Final = "report:generate"
REPORT_EXPORT: Final = "report:export"

# -- Safety / Evacuation (Phase 2.5) ------------------------------------------
# Reserved here from day one so role editors can already grant them, even though
# the evacuation module ships in Phase 2.5 (after the DeepStream migration).
EVACUATION_TRIGGER: Final = "evacuation:trigger"
EVACUATION_READ: Final = "evacuation:read"
EVACUATION_CONFIRM_SAFE: Final = "evacuation:confirm_safe"
EVACUATION_GENERATE_REPORT: Final = "evacuation:generate_report"
MUSTER_POINT_MANAGE: Final = "muster_point:manage"

# -- System administration ----------------------------------------------------
# These are reserved for the super_admin (TaxJar staff) — not exposed to tenants.
SYSTEM_TENANT_MANAGE: Final = "system:tenant_manage"
SYSTEM_BILLING_MANAGE: Final = "system:billing_manage"
SYSTEM_AUDIT_VIEW: Final = "system:audit_view"


PERMISSION_CATALOG: list[dict[str, str]] = [
    # Tenants
    {"key": TENANT_READ, "group": "Tenant", "label": "View tenant settings"},
    {"key": TENANT_UPDATE, "group": "Tenant", "label": "Update tenant settings"},
    # Users
    {"key": USER_READ, "group": "Users", "label": "View users"},
    {"key": USER_CREATE, "group": "Users", "label": "Create users"},
    {"key": USER_UPDATE, "group": "Users", "label": "Update users"},
    {"key": USER_DELETE, "group": "Users", "label": "Delete users"},
    {"key": USER_INVITE, "group": "Users", "label": "Invite users by email"},
    # Roles
    {"key": ROLE_READ, "group": "Roles", "label": "View roles"},
    {"key": ROLE_CREATE, "group": "Roles", "label": "Create custom roles"},
    {"key": ROLE_UPDATE, "group": "Roles", "label": "Edit roles and permissions"},
    {"key": ROLE_DELETE, "group": "Roles", "label": "Delete custom roles"},
    {"key": ROLE_ASSIGN, "group": "Roles", "label": "Assign roles to users"},
    # Sites
    {"key": SITE_READ, "group": "Sites", "label": "View sites"},
    {"key": SITE_CREATE, "group": "Sites", "label": "Create sites"},
    {"key": SITE_UPDATE, "group": "Sites", "label": "Update sites"},
    {"key": SITE_DELETE, "group": "Sites", "label": "Delete sites"},
    # Cameras
    {"key": CAMERA_READ, "group": "Cameras", "label": "View cameras"},
    {"key": CAMERA_CREATE, "group": "Cameras", "label": "Add cameras"},
    {"key": CAMERA_UPDATE, "group": "Cameras", "label": "Update camera config"},
    {"key": CAMERA_DELETE, "group": "Cameras", "label": "Remove cameras"},
    {"key": CAMERA_CALIBRATE, "group": "Cameras", "label": "Calibrate cameras"},
    {"key": CAMERA_STREAM_VIEW, "group": "Cameras", "label": "View live camera streams"},
    # Zones
    {"key": ZONE_READ, "group": "Zones", "label": "View zones"},
    {"key": ZONE_CREATE, "group": "Zones", "label": "Draw new zones"},
    {"key": ZONE_UPDATE, "group": "Zones", "label": "Edit zones and rules"},
    {"key": ZONE_DELETE, "group": "Zones", "label": "Delete zones"},
    # Employees
    {"key": EMPLOYEE_READ, "group": "Employees", "label": "View employee roster"},
    {"key": EMPLOYEE_CREATE, "group": "Employees", "label": "Add employees"},
    {"key": EMPLOYEE_UPDATE, "group": "Employees", "label": "Update employees"},
    {"key": EMPLOYEE_DELETE, "group": "Employees", "label": "Delete employees"},
    {"key": EMPLOYEE_ENROLL, "group": "Employees", "label": "Enroll face / appearance"},
    # Tracks
    {"key": TRACK_READ, "group": "Tracks", "label": "View live and historical tracks"},
    {"key": TRACK_REPLAY, "group": "Tracks", "label": "Replay tracks on floor plan"},
    # Live Wall
    {"key": LIVE_WALL_MANAGE_PRESETS, "group": "Live Wall", "label": "Create, edit, and delete wall presets"},
    # Floor Plans
    {"key": FLOOR_PLAN_READ, "group": "Floor Plans", "label": "View floor plans"},
    {"key": FLOOR_PLAN_CREATE, "group": "Floor Plans", "label": "Upload floor plans"},
    {"key": FLOOR_PLAN_UPDATE, "group": "Floor Plans", "label": "Edit floor plan metadata"},
    {"key": FLOOR_PLAN_DELETE, "group": "Floor Plans", "label": "Delete floor plans"},
    # Events
    {"key": EVENT_READ, "group": "Events", "label": "View events"},
    {"key": EVENT_EXPORT, "group": "Events", "label": "Export event data"},
    # Alerts
    {"key": ALERT_READ, "group": "Alerts", "label": "View alerts"},
    {"key": ALERT_ACKNOWLEDGE, "group": "Alerts", "label": "Acknowledge alerts"},
    {"key": ALERT_RESOLVE, "group": "Alerts", "label": "Resolve alerts"},
    {"key": ALERT_ASSIGN, "group": "Alerts", "label": "Assign alerts to operators"},
    {"key": ALERT_RULE_READ, "group": "Alerts", "label": "View alert rules"},
    {"key": ALERT_RULE_CREATE, "group": "Alerts", "label": "Create alert rules"},
    {"key": ALERT_RULE_UPDATE, "group": "Alerts", "label": "Update alert rules"},
    {"key": ALERT_RULE_DELETE, "group": "Alerts", "label": "Delete alert rules"},
    # Recordings
    {"key": RECORDING_READ, "group": "Recordings", "label": "View recordings"},
    {"key": RECORDING_EXPORT, "group": "Recordings", "label": "Export recording clips"},
    {"key": RECORDING_DELETE, "group": "Recordings", "label": "Delete recordings"},
    # Analytics
    {"key": ANALYTICS_READ, "group": "Analytics", "label": "View analytics dashboards"},
    {"key": REPORT_GENERATE, "group": "Analytics", "label": "Generate reports"},
    {"key": REPORT_EXPORT, "group": "Analytics", "label": "Export reports (PDF / Excel)"},
    # Safety / Evacuation (Phase 2.5)
    {"key": EVACUATION_TRIGGER, "group": "Safety", "label": "Trigger evacuation mode"},
    {"key": EVACUATION_READ, "group": "Safety", "label": "View evacuation status and history"},
    {"key": EVACUATION_CONFIRM_SAFE, "group": "Safety", "label": "Confirm person safe at muster point"},
    {"key": EVACUATION_GENERATE_REPORT, "group": "Safety", "label": "Generate post-drill reports"},
    {"key": MUSTER_POINT_MANAGE, "group": "Safety", "label": "Configure muster points"},
]


ALL_PERMISSIONS: set[str] = {p["key"] for p in PERMISSION_CATALOG}


# -- System (super_admin) permissions — separate catalog -----------------------
SYSTEM_PERMISSIONS: set[str] = {
    SYSTEM_TENANT_MANAGE,
    SYSTEM_BILLING_MANAGE,
    SYSTEM_AUDIT_VIEW,
}


# -- Default seeded roles ------------------------------------------------------
# These are created for every new tenant. The tenant_admin can then clone
# and customise them, or create entirely new roles from scratch.
DEFAULT_ROLES: list[dict] = [
    {
        "name": "Tenant Admin",
        "description": "Full access to all tenant resources",
        "is_system": True,
        "permissions": sorted(ALL_PERMISSIONS),
    },
    {
        "name": "Supervisor",
        "description": "Manages operations, reviews alerts and reports",
        "is_system": True,
        "permissions": sorted([
            SITE_READ, CAMERA_READ, CAMERA_STREAM_VIEW,
            ZONE_READ, ZONE_CREATE, ZONE_UPDATE, ZONE_DELETE,
            EMPLOYEE_READ, TRACK_READ, TRACK_REPLAY, EVENT_READ, EVENT_EXPORT,
            ALERT_READ, ALERT_ACKNOWLEDGE, ALERT_RESOLVE, ALERT_ASSIGN,
            ALERT_RULE_READ, ALERT_RULE_CREATE, ALERT_RULE_UPDATE,
            RECORDING_READ, RECORDING_EXPORT,
            ANALYTICS_READ, REPORT_GENERATE, REPORT_EXPORT,
            USER_READ,
            LIVE_WALL_MANAGE_PRESETS,
            FLOOR_PLAN_READ, FLOOR_PLAN_CREATE, FLOOR_PLAN_UPDATE, FLOOR_PLAN_DELETE,
            EVACUATION_TRIGGER, EVACUATION_READ, EVACUATION_CONFIRM_SAFE,
            EVACUATION_GENERATE_REPORT, MUSTER_POINT_MANAGE,
        ]),
    },
    {
        "name": "Operator",
        "description": "Monitors live feeds and responds to alerts",
        "is_system": True,
        "permissions": sorted([
            SITE_READ, CAMERA_READ, CAMERA_STREAM_VIEW, ZONE_READ,
            EMPLOYEE_READ, TRACK_READ,
            EVENT_READ, ALERT_READ, ALERT_ACKNOWLEDGE,
            RECORDING_READ,
            FLOOR_PLAN_READ,
            EVACUATION_READ, EVACUATION_CONFIRM_SAFE,
        ]),
    },
    {
        "name": "Viewer",
        "description": "Read-only access to reports and analytics",
        "is_system": True,
        "permissions": sorted([
            SITE_READ, CAMERA_READ, ZONE_READ, EMPLOYEE_READ,
            EVENT_READ, ALERT_READ, RECORDING_READ,
            ANALYTICS_READ, REPORT_GENERATE,
        ]),
    },
]
