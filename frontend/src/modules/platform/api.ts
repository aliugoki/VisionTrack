import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { useAuth, type CurrentUser } from '@/shared/hooks/useAuth';

export interface PlatformTenant {
  id: string;
  name: string;
  subdomain: string;
  external_company_id: string | null;
  plan: string;
  timezone: string;
  recording_retention_days: number;
  is_active: boolean;
  employee_count: number;
  camera_count: number;
  user_count: number;
}

export interface PlatformTenantUpdate {
  name?: string;
  is_active?: boolean;
  plan?: string;
  timezone?: string;
  recording_retention_days?: number;
}

const KEY = ['platform', 'tenants'] as const;

export function usePlatformTenants(enabled = true) {
  return useQuery({
    queryKey: KEY,
    enabled,
    queryFn: async () => {
      const { data } = await api.get<{ total: number; rows: PlatformTenant[] }>(
        '/platform/tenants',
      );
      return data;
    },
  });
}

export function useUpdateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...patch }: { id: string } & PlatformTenantUpdate) => {
      const { data } = await api.patch<PlatformTenant>(`/platform/tenants/${id}`, patch);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/platform/tenants/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

/** Enter a tenant (impersonate its admin) — swaps the active token, stashing the
 *  platform token so you can exit/switch. Returns an async enter(tenant) fn. */
export function useEnterTenant() {
  const { beginActing, setUser } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  return async (tenant: { id: string; name: string }) => {
    const { data: tok } = await api.post<{ access_token: string; refresh_token: string }>(
      `/platform/tenants/${tenant.id}/enter`,
    );
    beginActing(tok.access_token, tok.refresh_token, { id: tenant.id, name: tenant.name });
    const me = await api.get<CurrentUser>('/users/me');
    setUser(me.data);
    qc.clear();
    navigate('/');
  };
}
