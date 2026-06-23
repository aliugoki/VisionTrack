/**
 * Planar homography helpers for Bird's-Eye-View.
 *
 * A homography H is a 3x3 matrix (row-major, 9 numbers) mapping a point in
 * the camera's source-pixel image space to fractional (0..1) coordinates on
 * a floor plan:
 *
 *     [X*w]   [h0 h1 h2] [x]
 *     [Y*w] = [h3 h4 h5] [y]
 *     [ w ]   [h6 h7 h8] [1]
 *
 * We solve H from exactly 4 point correspondences (the minimum for a planar
 * homography) by fixing h8 = 1 and solving the resulting 8x8 linear system.
 */

export type Point = [number, number];
export type Homography = number[]; // length 9, row-major

/** Solve an n×n linear system A·x = b via Gaussian elimination with partial
 *  pivoting. Returns x, or null if the system is (near-)singular. */
function solveLinear(A: number[][], b: number[]): number[] | null {
  const n = b.length;
  // Augmented matrix
  const M = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    // Partial pivot
    let pivot = col;
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[pivot][col])) pivot = r;
    }
    if (Math.abs(M[pivot][col]) < 1e-12) return null; // singular
    [M[col], M[pivot]] = [M[pivot], M[col]];
    // Eliminate
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const factor = M[r][col] / M[col][col];
      for (let c = col; c <= n; c++) M[r][c] -= factor * M[col][c];
    }
  }
  return M.map((row, i) => row[n] / row[i]);
}

/**
 * Compute the homography mapping `src[i]` -> `dst[i]` from 4 correspondences.
 * Returns a row-major 9-element matrix, or null if the points are degenerate
 * (e.g. collinear).
 */
export function solveHomography(src: Point[], dst: Point[]): Homography | null {
  if (src.length < 4 || dst.length < 4) return null;
  const A: number[][] = [];
  const b: number[] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i];
    const [u, v] = dst[i];
    // u-row: x*h0 + y*h1 + h2 - u*x*h6 - u*y*h7 = u
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    b.push(u);
    // v-row: x*h3 + y*h4 + h5 - v*x*h6 - v*y*h7 = v
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    b.push(v);
  }
  const h = solveLinear(A, b);
  if (!h || h.some((v) => !Number.isFinite(v))) return null;
  return [...h, 1];
}

/** Apply a homography to an (x, y) point. Returns null if the point maps to
 *  the plane at infinity (w ≈ 0). */
export function projectPoint(H: Homography, x: number, y: number): Point | null {
  const w = H[6] * x + H[7] * y + H[8];
  if (Math.abs(w) < 1e-9) return null;
  return [
    (H[0] * x + H[1] * y + H[2]) / w,
    (H[3] * x + H[4] * y + H[5]) / w,
  ];
}

/** Foot point of a person bbox = bottom-center, the contact-with-floor point. */
export function footPoint(bbox: [number, number, number, number]): Point {
  const [x1, , x2, y2] = bbox;
  return [(x1 + x2) / 2, y2];
}

/** Read a stored camera.calibration JSON into a typed homography, or null. */
export interface StoredCalibration {
  floor_plan_id: string;
  homography: number[];
  image_ref: { width: number; height: number };
  src_points: number[][];
  dst_points: number[][];
  calibrated_at?: string;
}

export function readCalibration(
  calibration: Record<string, unknown> | null | undefined
): StoredCalibration | null {
  if (!calibration) return null;
  const h = calibration.homography as number[] | undefined;
  const fp = calibration.floor_plan_id as string | undefined;
  if (!Array.isArray(h) || h.length !== 9 || !fp) return null;
  return calibration as unknown as StoredCalibration;
}
