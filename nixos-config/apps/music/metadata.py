import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Optional

PIPE_PATH = "/tmp/shairport-sync-metadata"

# shairport-sync 4-char codes (hex-encoded in the pipe)
_CODE_TITLE  = "6d696e6d"  # minm
_CODE_ARTIST = "61736172"  # asar
_CODE_ALBUM  = "6173616c"  # asal
_CODE_ART    = "50494354"  # PICT
_CODE_START  = "70626567"  # pbeg — play session begin
_CODE_STOP   = "70656e64"  # pend — play session end


@dataclass
class TrackInfo:
    title:  str = ""
    artist: str = ""
    album:  str = ""
    art:    Optional[bytes] = field(default=None, repr=False)


class MetadataReader(threading.Thread):
    """Reads shairport-sync metadata from the named pipe in a background thread.

    Calls `on_update(TrackInfo)` on the main thread via the Qt signal bridge
    provided at construction time (a callable that posts to the Qt event loop).
    """

    def __init__(self, on_update: Callable[[TrackInfo], None]):
        super().__init__(daemon=True)
        self._on_update = on_update
        self._current   = TrackInfo()

    def run(self):
        while True:
            try:
                with open(PIPE_PATH, "rb") as pipe:
                    buf = b""
                    for raw in pipe:
                        buf += raw
                        # shairport-sync wraps each item in <item>...</item>
                        while b"</item>" in buf:
                            start = buf.find(b"<item>")
                            end   = buf.find(b"</item>") + len(b"</item>")
                            if start == -1:
                                buf = buf[end:]
                                continue
                            chunk = buf[start:end]
                            buf   = buf[end:]
                            self._parse(chunk)
            except OSError:
                # Pipe doesn't exist yet or was closed — retry silently
                import time; time.sleep(1)

    def _parse(self, chunk: bytes):
        try:
            item = ET.fromstring(chunk)
        except ET.ParseError:
            return

        code   = (item.findtext("code") or "").lower()
        data_el = item.find("data")
        if data_el is None:
            return

        encoding = data_el.get("encoding", "")
        raw      = data_el.text or ""

        if encoding == "base64":
            import base64
            value_bytes = base64.b64decode(raw)
            value_str   = value_bytes.decode("utf-8", errors="replace")
        else:
            value_bytes = bytes.fromhex(raw) if raw else b""
            value_str   = value_bytes.decode("utf-8", errors="replace")

        changed = False

        if code == _CODE_TITLE and value_str != self._current.title:
            self._current.title = value_str
            changed = True
        elif code == _CODE_ARTIST and value_str != self._current.artist:
            self._current.artist = value_str
            changed = True
        elif code == _CODE_ALBUM and value_str != self._current.album:
            self._current.album = value_str
            changed = True
        elif code == _CODE_ART:
            self._current.art = value_bytes if value_bytes else None
            changed = True
        elif code in (_CODE_START,):
            self._current = TrackInfo()
            changed = True
        elif code in (_CODE_STOP,):
            self._current = TrackInfo()
            changed = True

        if changed:
            import copy
            self._on_update(copy.copy(self._current))
