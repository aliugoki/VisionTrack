import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Tenant, TenantUpdate } from '@/modules/settings/types';

export const TENANT_KEYS = {
  me: ['tenant', 'me'] as const,
};

export function useTenant() {
  return useQuery({
    queryKey: TENANT_KEYS.me,
    queryFn: async () => {
      const { data } = await api.get<Tenant>('/tenants/me');
      return data;
    },
  });
}

export function useUpdateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: TenantUpdate) => {
      const { data } = await api.patch<Tenant>('/tenants/me', payload);
      return data;
    },
    onSuccess: (updated) => {
      // Update the cache directly so the UI reflects the change immediately
      qc.setQueryData(TENANT_KEYS.me, updated);
    },
  });
}
