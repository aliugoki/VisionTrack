/** Track event types — match backend Socket.IO emissions. */

export interface TrackBox {
  /** ByteTrack-assigned stable ID, unique per camera per session. */
  track_id: number;
  /** Bounding box in source pixel space: [x1, y1, x2, y2]. */
  bbox: [number, number, number, number];
  confidence: number;
  /** COCO class id. Currently always 0 (person). Reserved for future use. */
  class_id: number;
}

/** Payload of the "track_update" Socket.IO event — one per AI inference. */
export interface TrackUpdateEvent {
  type: 'track_update';
  camera_id: string;
  /** Wall-clock millis when the frame was captured by the AI worker. */
  frame_ts_ms: number;
  tracks: TrackBox[];
}

/** Payload of the "track_lifecycle" Socket.IO event. */
export interface TrackLifecycleEvent {
  type: 'track_lifecycle';
  camera_id: string;
  tracker_id: number;
  event: 'started' | 'ended';
  ts_ms: number;
}

/** A buffered frame snapshot used by the overlay's time-aligned renderer. */
export interface BufferedFrame {
  /** Wall-clock ms the frame was captured (frame_ts_ms from the event). */
  ts_ms: number;
  tracks: TrackBox[];
}
