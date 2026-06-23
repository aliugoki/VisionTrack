import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  FloorPlan,
  FloorPlanMarker,
  Zone,
  FloorPlanUpdate,
} from '@/modules/floor-plan/types';

const KEY = ['floor-plans'] as const;

export function useFloorPlans(siteId?: string) {
  return useQuery({
    queryKey: [...KEY, siteId ?? null],
    queryFn: async () => {
      const { data } = await api.get<FloorPlan[]>('/floor-plans', {
        params: siteId ? { site_id: siteId } : undefined,
      });
      return data;
    },
  });
}

export function useFloorPlan(id: string | null | undefined) {
  return useQuery({
    queryKey: [...KEY, 'one', id],
    queryFn: async () => {
      const { data } = await api.get<FloorPlan>(`/floor-plans/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export interface UploadFloorPlanInput {
  site_id: string;
  name: string;
  description?: string | null;
  file: File;
}

export function useUploadFloorPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      site_id,
      name,
      description,
      file,
    }: UploadFloorPlanInput) => {
      const form = new FormData();
      form.append('site_id', site_id);
      form.append('name', name);
      if (description) form.append('description', description);
      form.append('file', file);
      const { data } = await api.post<FloorPlan>('/floor-plans', form, {
        // Let axios + browser set the multipart boundary automatically.
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateFloorPlan(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: FloorPlanUpdate) => {
      const { data } = await api.patch<FloorPlan>(
        `/floor-plans/${id}`,
        payload
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateFloorPlanMarkers(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (markers: FloorPlanMarker[]) => {
      const { data } = await api.patch<FloorPlan>(
        `/floor-plans/${id}/markers`,
        { markers }
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

/**
 * Replace the full zone set on a floor plan.
 * Atomic-replace: the editor PUTs the complete list at once.
 * Server validates polygon shape, hex color, and rule schema.
 */
export function useUpdateFloorPlanZones(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (zones: Zone[]) => {
      const { data } = await api.put<FloorPlan>(
        `/floor-plans/${id}/zones`,
        { zones }
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteFloorPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/floor-plans/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

/**
 * Build the URL the browser can fetch a floor plan image from. Uses the
 * axios client's baseURL so it works with both the Vite dev proxy and
 * production deployments.
 *
 * The endpoint requires auth, so we can't just <img src> it. The viewer
 * component uses fetch+blob URL or includes the auth header explicitly.
 */
export function floorPlanImageUrl(id: string): string {
  return `${api.defaults.baseURL ?? ''}/floor-plans/${id}/image`;
}
