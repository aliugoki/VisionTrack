import { useMemo } from 'react';
import type { Camera } from '@/shared/types/api';
import type { TileEntry } from '@/modules/live-wall/types';

/**
 * NVENC session pressure on consumer NVIDIA GPUs.
 *
 * Each H.265 camera in the wall needs one NVENC session for browser-side
 * H.264 transcoding (MediaMTX → ffmpeg → HLS). RTX 3070 / 4060 cap at 5
 * concurrent sessions. H.264 cameras consume zero NVENC sessions.
 *
 * Levels:
 *   ok       — 0-3 H.265 cameras, no concern
 *   warn     — 4 H.265 cameras, one away from the limit
 *   exceeded — 5+ H.265 cameras, transcodes will fail
 */
export type NvencLevel = 'ok' | 'warn' | 'exceeded';

export interface NvencEstimate {
  h265Count: number;
  h264Count: number;
  level: NvencLevel;
  limit: number;
}

const NVENC_CONSUMER_LIMIT = 5;
const WARN_THRESHOLD = 4;

export function useNvencEstimate(
  tiles: TileEntry[],
  cameras: Camera[] | undefined
): NvencEstimate {
  return useMemo(() => {
    let h265 = 0;
    let h264 = 0;
    if (!cameras) {
      return { h265Count: 0, h264Count: 0, level: 'ok', limit: NVENC_CONSUMER_LIMIT };
    }
    const byId = new Map(cameras.map((c) => [c.id, c]));
    for (const tileId of tiles) {
      if (!tileId) continue;
      const cam = byId.get(tileId);
      if (!cam) continue;
      if (cam.codec === 'H265') h265++;
      else h264++;
    }
    const level: NvencLevel =
      h265 >= NVENC_CONSUMER_LIMIT
        ? 'exceeded'
        : h265 >= WARN_THRESHOLD
          ? 'warn'
          : 'ok';
    return { h265Count: h265, h264Count: h264, level, limit: NVENC_CONSUMER_LIMIT };
  }, [tiles, cameras]);
}
