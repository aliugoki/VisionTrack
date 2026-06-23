import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Camera } from '@/shared/types/api';

/** Payload for PUT /cameras/{id}/calibration — mirrors backend CameraCalibration. */
export interface CalibrationPayload {
  floor_plan_id: string;
  homography: number[]; // row-major 3x3
  image_ref: { width: number; height: number };
  src_points: number[][]; // source-pixel correspondences
  dst_points: number[][]; // floor-plan fractional correspondences
}

/** Persist a camera's BEV homography. Invalidates the cameras cache so the
 *  live view picks up the new calibration. */
export function useSetCameraCalibration(cameraId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CalibrationPayload) => {
      const { data } = await api.put<Camera>(
        `/cameras/${cameraId}/calibration`,
        payload
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cameras'] });
    },
  });
}
