import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

/** Mirror of backend TrackRead. */
export interface TrackRead {
  id: string;
  tenant_id: string;
  camera_id: string;
  tracker_id: number;
  started_at: string;
  ended_at: string | null;
  first_bbox: Record<string, number>;
  last_bbox: Record<string, number>;
  point_count: number;
  /** Nullable until P2.5 matcher attributes the track to a person. */
  person_id?: string | null;
}

const ACTIVE_TRACKS_KEY = ['tracks', 'active'] as const;

/**
 * Tracks currently being detected (ended_at IS NULL) for a given camera.
 * Polls every 5s. Updates fast enough for an operator-facing widget
 * without hammering the API.
 */
export function useActiveTracksByCamera(cameraId: string | undefined) {
  return useQuery({
    queryKey: [...ACTIVE_TRACKS_KEY, cameraId],
    enabled: !!cameraId,
    queryFn: async () => {
      const { data } = await api.get<TrackRead[]>('/tracks/active', {
        params: { camera_id: cameraId },
      });
      return data;
    },
    refetchInterval: 5_000,
    staleTime: 2_000,
  });
}
