/**
 * Mirror of backend UserRead / UserCreate / UserUpdate schemas.
 * Source: backend/app/modules/users/schemas.py
 */

export interface Role {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  locale: 'en' | 'ar';
  is_active: boolean;
  is_superuser: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  roles: Role[];
}

export interface UserCreate {
  email: string;
  full_name: string;
  locale: 'en' | 'ar';
  is_active: boolean;
  password: string;
  role_ids: string[];
}

export interface UserUpdate {
  full_name?: string;
  locale?: 'en' | 'ar';
  is_active?: boolean;
  role_ids?: string[];
}
