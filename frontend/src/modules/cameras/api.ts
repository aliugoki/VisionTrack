import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type {
  Camera,
  CameraCreate,
  CameraDiscoveryRequest,
  CameraDiscoveryResult,
  CameraUpdate,
} from '@/shared/types/api';

const CAMERAS_KEY = ['cameras'] as const;

export function useCameras(params?: {
  site_id?: string;
  status?: string;
  search?: string;
}) {
  return useQuery({
    queryKey: [...CAMERAS_KEY, params],
    queryFn: async () => {
      const { data } = await api.get<Camera[]>('/cameras', { params });
      return data;
    },
    refetchInterval: 15_000, // status changes update in the list view
  });
}

export function useCamera(id: string | undefined) {
  return useQuery({
    queryKey: [...CAMERAS_KEY, id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<Camera>(`/cameras/${id}`);
      return data;
    },
  });
}

export function useCreateCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CameraCreate) => {
      const { data } = await api.post<Camera>('/cameras', payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useUpdateCamera(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CameraUpdate) => {
      const { data } = await api.patch<Camera>(`/cameras/${id}`, payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useDeleteCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/cameras/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useDiscoverCameras() {
  return useMutation({
    mutationFn: async (payload: CameraDiscoveryRequest = {}) => {
      const { data } = await api.post<CameraDiscoveryResult[]>(
        '/cameras/discover',
        payload
      );
      return data;
    },
  });
}
