import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  WallPreset,
  WallPresetCreate,
  WallPresetUpdate,
} from '@/modules/live-wall/types';

const PRESETS_KEY = ['wall-presets'] as const;

export function useWallPresets() {
  return useQuery({
    queryKey: PRESETS_KEY,
    queryFn: async () => {
      const { data } = await api.get<WallPreset[]>('/live-wall/presets');
      return data;
    },
  });
}

export function useCreateWallPreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: WallPresetCreate) => {
      const { data } = await api.post<WallPreset>(
        '/live-wall/presets',
        payload
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: PRESETS_KEY }),
  });
}

export function useUpdateWallPreset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: WallPresetUpdate) => {
      const { data } = await api.patch<WallPreset>(
        `/live-wall/presets/${id}`,
        payload
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: PRESETS_KEY }),
  });
}

export function useDeleteWallPreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/live-wall/presets/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: PRESETS_KEY }),
  });
}
