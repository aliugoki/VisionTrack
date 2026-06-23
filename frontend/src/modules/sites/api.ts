import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Site, SiteCreate } from '@/shared/types/api';

const SITES_KEY = ['sites'] as const;

export function useSites() {
  return useQuery({
    queryKey: SITES_KEY,
    queryFn: async () => {
      const { data } = await api.get<Site[]>('/sites');
      return data;
    },
  });
}

export function useCreateSite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: SiteCreate) => {
      const { data } = await api.post<Site>('/sites', payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: SITES_KEY }),
  });
}
