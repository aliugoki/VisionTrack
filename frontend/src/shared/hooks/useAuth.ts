import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  locale: string;
  is_superuser: boolean;
  roles: Array<{ id: string; name: string; permissions: string[] }>;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUser | null;
  permissions: Set<string>;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: CurrentUser) => void;
  clear: () => void;
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

      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),

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
