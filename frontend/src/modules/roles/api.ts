import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  PermissionCatalogItem,
  Role,
  RoleCreate,
  RoleUpdate,
} from '@/modules/roles/types';

export const ROLE_KEYS = {
  all: ['roles'] as const,
  list: ['roles', 'list'] as const,
  detail: (id: string) => ['roles', 'detail', id] as const,
  catalog: ['roles', 'permissions-catalog'] as const,
};

// ---- queries ----

export function useRoles() {
  return useQuery({
    queryKey: ROLE_KEYS.list,
    queryFn: async () => {
      const { data } = await api.get<Role[]>('/roles');
      return data;
    },
  });
}

export function useRole(id: string | null | undefined) {
  return useQuery({
    queryKey: ROLE_KEYS.detail(id || ''),
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<Role>(`/roles/${id}`);
      return data;
    },
  });
}

/**
 * Permission catalog — the full list of permissions with their group +
 * human label, used to build the permission matrix in the role editor.
 * Catalog doesn't change at runtime so we cache it aggressively.
 */
export function usePermissionsCatalog() {
  return useQuery({
    queryKey: ROLE_KEYS.catalog,
    staleTime: 1000 * 60 * 30, // 30 minutes
    queryFn: async () => {
      const { data } = await api.get<PermissionCatalogItem[]>(
        '/roles/permissions'
      );
      return data;
    },
  });
}

// ---- mutations ----

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RoleCreate) => {
      const { data } = await api.post<Role>('/roles', payload);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ROLE_KEYS.list });
    },
  });
}

export function useUpdateRole(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RoleUpdate) => {
      const { data } = await api.patch<Role>(`/roles/${id}`, payload);
      return data;
    },
    onSuccess: (updated) => {
      qc.setQueryData(ROLE_KEYS.detail(updated.id), updated);
      qc.invalidateQueries({ queryKey: ROLE_KEYS.list });
    },
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/roles/${id}`);
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ROLE_KEYS.list });
    },
  });
}
