/**
 * Mirror of backend RoleRead / RoleCreate / RoleUpdate +
 * PermissionCatalogItem schemas.
 *
 * Source of truth:
 *   backend/app/modules/roles/schemas.py
 *   backend/app/core/permissions.py
 */

export interface Role {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoleCreate {
  name: string;
  description?: string | null;
  permissions: string[];
}

export interface RoleUpdate {
  name?: string;
  description?: string | null;
  permissions?: string[];
}

export interface PermissionCatalogItem {
  key: string;
  group: string;
  label: string;
}
