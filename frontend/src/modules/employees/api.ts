import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface EmployeeRow {
  id: string;
  emp_id: string;
  name: string;
  external_company_id: string | null;
  source: string;
  synced_at: string | null;
  seen: boolean;
}

export interface EmployeeListResponse {
  total: number;
  rows: EmployeeRow[];
}

export function useEmployees(search?: string) {
  return useQuery({
    queryKey: ['employees', search ?? ''] as const,
    queryFn: async () => {
      const { data } = await api.get<EmployeeListResponse>('/employees', {
        params: search ? { search } : undefined,
      });
      return data;
    },
  });
}
