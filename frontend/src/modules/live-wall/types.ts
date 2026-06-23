/** Live Wall types — match backend schemas in app/modules/live_wall/schemas.py */

/** Supported grid dimensions. Keep in sync with backend's SUPPORTED_GRIDS. */
export const LAYOUTS = [
  { rows: 1, cols: 1, label: '1×1' },
  { rows: 2, cols: 2, label: '2×2' },
  { rows: 3, cols: 3, label: '3×3' },
  { rows: 4, cols: 4, label: '4×4' },
] as const;

export type LayoutDims = (typeof LAYOUTS)[number];

/** A tile is either a camera UUID string or null (empty). */
export type TileEntry = string | null;

export interface WallPreset {
  id: string;
  tenant_id: string;
  created_by_user_id: string | null;
  name: string;
  description: string | null;
  rows: 1 | 2 | 3 | 4;
  cols: 1 | 2 | 3 | 4;
  tiles: TileEntry[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface WallPresetCreate {
  name: string;
  description?: string | null;
  rows: 1 | 2 | 3 | 4;
  cols: 1 | 2 | 3 | 4;
  tiles: TileEntry[];
  is_default?: boolean;
}

export interface WallPresetUpdate {
  name?: string;
  description?: string | null;
  rows?: 1 | 2 | 3 | 4;
  cols?: 1 | 2 | 3 | 4;
  tiles?: TileEntry[];
  is_default?: boolean;
}
