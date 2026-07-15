import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  locale: string;
  is_superuser: boolean;
  is_platform_admin?: boolean;
  roles: Array<{ id: string; name: string; permissions: string[] }>;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUser | null;
  permissions: Set<string>;
  // Platform admin "enter tenant": the original platform token is stashed so we
  // can switch/exit; actingTenant marks that we're impersonating a tenant.
  platformAccess: string | null;
  platformRefresh: string | null;
  actingTenant: { id: string; name: string } | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: CurrentUser) => void;
  clear: () => void;
  beginActing: (access: string, refresh: string, tenant: { id: string; name: string }) => void;
  stopActing: () => void;
  hasPermission: (perm: string) => boolean;
  hasAnyPermission: (...perms: string[]) => boolean;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      permissions: new Set(),
      platformAccess: null,
      platformRefresh: null,
      actingTenant: null,

      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),

      beginActing: (access, refresh, tenant) =>
        set((state) => ({
          // Stash the platform token the first time we enter a tenant.
          platformAccess: state.actingTenant ? state.platformAccess : state.accessToken,
          platformRefresh: state.actingTenant ? state.platformRefresh : state.refreshToken,
          accessToken: access,
          refreshToken: refresh,
          actingTenant: tenant,
        })),

      stopActing: () =>
        set((state) => ({
          accessToken: state.platformAccess,
          refreshToken: state.platformRefresh,
          platformAccess: null,
          platformRefresh: null,
          actingTenant: null,
        })),

      setUser: (user) => {
        const perms = new Set<string>();
        for (const role of user.roles) {
          for (const p of role.permissions) perms.add(p);
        }
        set({ user, permissions: perms });
      },

      clear: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          permissions: new Set(),
          platformAccess: null,
          platformRefresh: null,
          actingTenant: null,
        }),

      hasPermission: (perm) => {
        const u = get().user;
        if (u?.is_superuser) return true;
        return get().permissions.has(perm);
      },

      hasAnyPermission: (...perms) => {
        const u = get().user;
        if (u?.is_superuser) return true;
        const userPerms = get().permissions;
        return perms.some((p) => userPerms.has(p));
      },
    }),
    {
      name: 'visiontrack-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        platformAccess: state.platformAccess,
        platformRefresh: state.platformRefresh,
        actingTenant: state.actingTenant,
      }),
      onRehydrateStorage: () => (state) => {
        // Rebuild the permissions Set after rehydrating from localStorage
        if (state?.user) {
          const perms = new Set<string>();
          for (const role of state.user.roles) {
            for (const p of role.permissions) perms.add(p);
          }
          state.permissions = perms;
        }
      },
    }
  )
);
