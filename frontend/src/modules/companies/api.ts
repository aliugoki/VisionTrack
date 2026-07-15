import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface Company {
  id: string;
  external_id: string | null;
  name: string;
  admin_username: string | null;
  status: string | null;
  source: string;
  is_active: boolean;
  synced_at: string | null;
  employee_count: number;
}

export interface CompanyListResponse {
  total: number;
  rows: Company[];
}

export interface CompanyInput {
  name: string;
  admin_username?: string | null;
  status?: string | null;
  is_active?: boolean;
}

const KEY = ['companies'] as const;

export function useCompanies() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await api.get<CompanyListResponse>('/companies');
      return data;
    },
  });
}

export function useCreateCompany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CompanyInput) => {
      const { data } = await api.post<Company>('/companies', payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateCompany(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<CompanyInput>) => {
      const { data } = await api.patch<Company>(`/companies/${id}`, payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteCompany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/companies/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
