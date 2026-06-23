import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Role, User, UserCreate, UserUpdate } from '@/modules/users/types';

export const USER_KEYS = {
  all: ['users'] as const,
  list: ['users', 'list'] as const,
  detail: (id: string) => ['users', 'detail', id] as const,
  roles: ['roles'] as const,
};

// ----- queries -----

export function useUsers() {
  return useQuery({
    queryKey: USER_KEYS.list,
    queryFn: async () => {
      const { data } = await api.get<User[]>('/users');
      return data;
    },
  });
}

export function useUser(id: string | null | undefined) {
  return useQuery({
    queryKey: USER_KEYS.detail(id || ''),
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<User>(`/users/${id}`);
      return data;
    },
  });
}

/**
 * Roles list — used by the UserFormDialog to render role checkboxes.
 * The roles module also uses this; we keep the key shared so both
 * consumers stay in sync after role edits.
 */
export function useRoles() {
  return useQuery({
    queryKey: USER_KEYS.roles,
    queryFn: async () => {
      const { data } = await api.get<Role[]>('/roles');
      return data;
    },
  });
}

// ----- mutations -----

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: UserCreate) => {
      const { data } = await api.post<User>('/users', {
        ...payload,
        email: payload.email.trim().toLowerCase(),
      });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: USER_KEYS.list });
    },
  });
}

export function useUpdateUser(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: UserUpdate) => {
      const { data } = await api.patch<User>(`/users/${id}`, payload);
      return data;
    },
    onSuccess: (updated) => {
      qc.setQueryData(USER_KEYS.detail(updated.id), updated);
      qc.invalidateQueries({ queryKey: USER_KEYS.list });
    },
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/users/${id}`);
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: USER_KEYS.list });
    },
  });
}
