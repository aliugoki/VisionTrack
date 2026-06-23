"""DeepStream batched pipeline.

ONE pipeline with N RTSP sources fed into nvstreammux. This is the
DS-native pattern — every frame from every camera goes through the same
inference batch on the GPU, giving us the throughput benefit that
DeepStream exists to provide.

Pipeline graph (P2.2):

    uridecodebin × N ──> nvstreammux ──> pgie (PeopleNet)
                                            │
                                            ▼
                                        nvtracker (NvDCF)
                                            │
                                            ▼
                                          fakesink

    Where N = number of online cameras at pipeline-build time.

For P2.2, we deliberately stop at nvtracker — no SGIE (ReID) wired in
yet, no probes attached, no Redis publishing. The goal of this batch
is to confirm GPU-side decoding + detection + tracking works against
both real cameras through MediaMTX. SGIE + probes + publishing arrive
in P2.3 and P2.4.

Rebuild semantics:
  When the camera list changes, we tear down the entire pipeline and
  rebuild it. Cameras don't churn (adds/removes are minutes/hours
  apart), so rebuilding is cheap compared to the engineering cost of
  hot-attaching sources via runtime_source_add_delete. We may revisit
  in P3 if needed.

GLib mainloop runs on a background thread; the supervisor in main.py
owns the asyncio event loop on the main thread.
"""

from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from app.camera_discovery import DiscoveredCamera
from app.config import settings
from app.logging_config import get_logger

log = get_logger("pipeline")


# One-time GStreamer init (safe to call multiple times but cheap to guard).
_gst_init_done = False
_gst_init_lock = threading.Lock()


def _ensure_gst_init() -> None:
    global _gst_init_done
    with _gst_init_lock:
        if not _gst_init_done:
            Gst.init(None)
            _gst_init_done = True


def _on_pad_added(decodebin, pad, sinkpad):
    """uridecodebin emits pads dynamically as it figures out the stream.
    We only care about video pads — drop audio (cameras may carry audio
    we don't need, hooking it up would just waste cycles)."""
    caps = pad.get_current_caps() or pad.query_caps(None)
    caps_str = caps.to_string() if caps else ""
    if not caps_str.startswith("video/"):
        return
    if sinkpad.is_linked():
        log.warning("pipeline.pad_already_linked", caps=caps_str[:60])
        return
    link_result = pad.link(sinkpad)
    if link_result != Gst.PadLinkReturn.OK:
        log.warning("pipeline.pad_link_failed", result=str(link_result))


def _bus_message_handler(_bus, message, loop: GLib.MainLoop) -> bool:
    """Surface pipeline-level errors / EOS to the log + stop the mainloop."""
    t = message.type
    if t == Gst.MessageType.EOS:
        log.warning("pipeline.eos")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, dbg = message.parse_error()
        log.error("pipeline.error", error=str(err), debug=dbg or "")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        warn, dbg = message.parse_warning()
        log.warning("pipeline.warning", warning=str(warn), debug=dbg or "")
    return True


class DeepStreamPipeline:
    """One DS pipeline supervising N cameras.

    Owns a GLib MainLoop running on its own thread. start() blocks until
    PLAYING state is reached or fails. stop() is idempotent and
    thread-safe.
    """

    def __init__(self, cameras: list[DiscoveredCamera]) -> None:
        if not cameras:
            raise ValueError("DeepStreamPipeline requires at least one camera")
        self._cameras = cameras
        self._pipeline: Gst.Pipeline | None = None
        self._loop: GLib.MainLoop | None = None
        self._loop_thread: threading.Thread | None = None
        # Map of nvstreammux sink-pad index → DiscoveredCamera, useful
        # later for tagging frame metadata with tenant_id (P2.4).
        self.source_id_to_camera: dict[int, DiscoveredCamera] = {}

    def _build_pipeline(self) -> Gst.Pipeline:
        """Construct the GStreamer pipeline graph."""
        _ensure_gst_init()
        pipeline = Gst.Pipeline.new("vt-ds-pipeline")

        # ---- Elements --------------------------------------------------------
        streammux = Gst.ElementFactory.make("nvstreammux", "streammux")
        if streammux is None:
            raise RuntimeError(
                "Failed to create nvstreammux. Is DeepStream installed in this container?"
            )
        streammux.set_property("batch-size", len(self._cameras))
        streammux.set_property("width", settings.DS_MUX_WIDTH)
        streammux.set_property("height", settings.DS_MUX_HEIGHT)
        streammux.set_property(
            "batched-push-timeout", settings.DS_BATCH_PUSH_TIMEOUT_US
        )
        streammux.set_property("live-source", settings.DS_LIVE_SOURCE)

        pgie = Gst.ElementFactory.make("nvinfer", "pgie")
        if pgie is None:
            raise RuntimeError("Failed to create nvinfer (pgie)")
        pgie.set_property("config-file-path", settings.PGIE_CONFIG_PATH)

        tracker = Gst.ElementFactory.make("nvtracker", "tracker")
        if tracker is None:
            raise RuntimeError("Failed to create nvtracker")
        self._configure_tracker(tracker)

        sink = Gst.ElementFactory.make("fakesink", "sink")
        if sink is None:
            raise RuntimeError("Failed to create fakesink")
        # qos=False so the sink doesn't drop frames; we want the
        # detection/tracking to run on every batched frame.
        sink.set_property("qos", False)
        sink.set_property("sync", False)

        for elem in (streammux, pgie, tracker, sink):
            pipeline.add(elem)

        # ---- Link the static chain ------------------------------------------
        if not streammux.link(pgie):
            raise RuntimeError("Failed to link streammux -> pgie")
        if not pgie.link(tracker):
            raise RuntimeError("Failed to link pgie -> tracker")
        if not tracker.link(sink):
            raise RuntimeError("Failed to link tracker -> sink")

        # ---- Sources --------------------------------------------------------
        for i, cam in enumerate(self._cameras):
            srcbin = Gst.ElementFactory.make("uridecodebin", f"src-{i}")
            if srcbin is None:
                raise RuntimeError(f"Failed to create uridecodebin for camera {cam.id}")
            srcbin.set_property("uri", cam.rtsp_url)
            pipeline.add(srcbin)

            sinkpad = streammux.request_pad_simple(f"sink_{i}")
            if sinkpad is None:
                # nvstreammux may use request_pad() on older DS versions.
                sinkpad = streammux.get_request_pad(f"sink_{i}")
            if sinkpad is None:
                raise RuntimeError(f"Could not request streammux sink_{i}")

            srcbin.connect(
                "pad-added", lambda db, p, sp=sinkpad: _on_pad_added(db, p, sp)
            )
            self.source_id_to_camera[i] = cam
            log.info(
                "pipeline.source_added",
                source_id=i,
                camera_id=str(cam.id),
                name=cam.name,
                rtsp=cam.rtsp_url,
            )

        return pipeline

    def _configure_tracker(self, tracker: Gst.Element) -> None:
        """Apply NvDCF tracker config.

        nvtracker reads its detailed settings from a YAML file referenced
        by `ll-config-file`. We also set a few top-level GStreamer props
        that aren't in the YAML.
        """
        # Use the default DCF library shipped with DS 7.1.
        tracker.set_property(
            "ll-lib-file",
            "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so",
        )
        tracker.set_property("ll-config-file", settings.TRACKER_CONFIG_PATH)
        # Resolution at which the tracker operates; mirrors streammux.
        tracker.set_property("tracker-width", settings.DS_MUX_WIDTH)
        tracker.set_property("tracker-height", settings.DS_MUX_HEIGHT)
        # GPU 0 — single GPU host.
        tracker.set_property("gpu-id", 0)

    def start(self) -> None:
        """Build + start the pipeline. Blocks until PLAYING state."""
        log.info("pipeline.starting", camera_count=len(self._cameras))
        self._pipeline = self._build_pipeline()

        # Bus message watch — runs on the GLib mainloop thread.
        self._loop = GLib.MainLoop()
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", _bus_message_handler, self._loop)

        # Transition to PLAYING. This is async in GStreamer — the function
        # returns immediately and the state change happens in the background.
        # Returns SUCCESS, ASYNC (waiting), NO_PREROLL (live source), or FAILURE.
        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Pipeline failed to reach PLAYING state")
        log.info("pipeline.state_change_requested", result=str(ret))

        # Run the GLib mainloop in a background thread; main.py's asyncio
        # loop continues to own the main thread.
        self._loop_thread = threading.Thread(
            target=self._run_loop, name="ds-gst-loop", daemon=True
        )
        self._loop_thread.start()
        log.info("pipeline.started")

    def _run_loop(self) -> None:
        try:
            assert self._loop is not None
            self._loop.run()
        except Exception as e:
            log.error("pipeline.loop_crashed", error=str(e))

    def stop(self) -> None:
        """Tear down the pipeline. Idempotent + thread-safe."""
        if self._pipeline is not None:
            log.info("pipeline.stopping")
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()
        if self._loop_thread is not None and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=5.0)
            if self._loop_thread.is_alive():
                log.warning("pipeline.loop_thread_did_not_exit")
        self._loop_thread = None
        self._loop = None
        log.info("pipeline.stopped")


def cameras_changed(
    a: list[DiscoveredCamera], b: list[DiscoveredCamera]
) -> bool:
    """Return True if the two camera lists differ enough to warrant rebuild.

    We compare by (id, rtsp_url) pairs because re-keying alone or a URL
    change both require a fresh pipeline.
    """
    return {(c.id, c.rtsp_url) for c in a} != {(c.id, c.rtsp_url) for c in b}
