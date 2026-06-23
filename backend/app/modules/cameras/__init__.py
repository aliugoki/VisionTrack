# Apply the MediaMTXClient.add_transcode_path monkey-patch on first import
# of this module. Without this, ensure_browser_path can't provision the
# H.264 transcode sibling needed for browser HLS playback of H.265 cameras.
from app.modules.cameras import mediamtx_transcode_patch  # noqa: F401
