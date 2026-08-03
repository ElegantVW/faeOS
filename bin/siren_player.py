import os
import socket
import json
import random
import subprocess
import time
from pathlib import Path
from mutagen import File as MutagenFile

PLAYLIST_DIR = Path.home() / ".config" / "siren" / "playlists"
PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)

MUSIC_DIR = Path.home() / "Music"
AUDIO_EXT = ('.mp3', '.flac', '.ogg', '.m4a', '.wav', '.opus', '.mp4', '.mkv', '.mka', '.aac', '.wma')


class Queue:
    """Session queue — stores track metadata at add-time so it survives file moves.
    On play, validates file exists; missing tracks are removed with notification.
    """
    def __init__(self):
        self.items: list[dict] = []  # each: {"path": str, "display": str, "title": str, "artist": str, "duration": float}

    def add(self, path: str, player: 'SirenPlayer' = None, prepend: bool = False) -> int:
        """Add track by path. Resolves metadata immediately.
        If prepend=True, inserts at front (play next)."""
        path = os.path.expanduser(path)
        if player is None:
            player = SirenPlayer()
        display = player.get_track_metadata(path)
        title = ""
        artist = ""
        try:
            audio = MutagenFile(path)
            if audio:
                title = player._clean_tag(audio, ["title", "TIT2"]) or ""
                artist = player._clean_tag(audio, ["artist", "TPE1"]) or ""
        except Exception:
            pass
        item = {"path": path, "display": display, "title": title, "artist": artist, "duration": 0.0}
        if prepend:
            self.items.insert(0, item)
        else:
            self.items.append(item)
        return len(self.items)

    def add_multiple(self, paths: list[str], player: 'SirenPlayer' = None, prepend: bool = False) -> int:
        for p in paths:
            self.add(p, player, prepend)
        return len(self.items)

    def remove(self, index: int) -> dict | None:
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None

    def move(self, from_idx: int, to_idx: int) -> bool:
        if 0 <= from_idx < len(self.items) and 0 <= to_idx < len(self.items):
            item = self.items.pop(from_idx)
            self.items.insert(to_idx, item)
            return True
        return False

    def clear(self):
        self.items.clear()

    def list(self) -> list[dict]:
        return self.items.copy()

    def validate_all(self, player: 'SirenPlayer') -> list[dict]:
        """Check all items exist. Return list of removed items with reasons."""
        removed = []
        valid = []
        for item in self.items:
            if os.path.exists(item["path"]):
                valid.append(item)
            else:
                removed.append({"item": item, "reason": "File not found"})
        self.items = valid
        return removed

    def __len__(self):
        return len(self.items)

    def __bool__(self):
        return bool(self.items)


class SirenPlayer:
    def __init__(self, socket_path="/tmp/mpv-music.sock", playlist_dir="~/.config/siren/playlists"):
        self.socket_path = socket_path
        self.playlist_dir = os.path.expanduser(playlist_dir)
        os.makedirs(self.playlist_dir, exist_ok=True)
        self.client = None

    # ==========================================
    # METADATA & FILE MANAGEMENT FUNCTIONS
    # ==========================================

    def _clean_tag(self, audio_obj, keys):
        """Helper to safely extract a clean string from mutagen tags."""
        for key in keys:
            tag_value = audio_obj.get(key)
            if tag_value:
                if isinstance(tag_value, (list, tuple)) and len(tag_value) > 0:
                    val = str(tag_value[0]).strip()
                else:
                    val = str(tag_value).strip()

                if val and val.lower() != "none":
                    return val
        return None

    def get_track_metadata(self, file_path):
        """
        Parses audio file tags using mutagen (cached by path + mtime).
        Returns a formatted string: "Artist - Title" or filename fallback.
        """
        if not file_path:
            return "Unknown Track"

        if file_path.startswith("file://"):
            file_path = file_path[7:]

        if not os.path.isfile(file_path):
            filename = os.path.splitext(os.path.basename(file_path))[0]
            return filename.replace("_", " ").replace("-", " - ")

        try:
            st = os.stat(file_path)
            cache_key = (file_path, st.st_mtime_ns)
            cached = _META_CACHE.get(cache_key)
            if cached is not None:
                return cached
        except OSError:
            cache_key = None

        display = None
        try:
            audio = MutagenFile(file_path)
            if audio is not None:
                title = self._clean_tag(audio, ["title", "TIT2"])
                artist = self._clean_tag(audio, ["artist", "TPE1"])
                if title and artist:
                    display = f"{artist} - {title}"
                elif title:
                    display = title
        except Exception:
            pass

        if not display:
            filename = os.path.splitext(os.path.basename(file_path))[0]
            display = filename.replace("_", " ").replace("-", " - ")

        if cache_key is not None:
            if len(_META_CACHE) >= _META_CACHE_MAX:
                _META_CACHE.clear()
            _META_CACHE[cache_key] = display
        return display

    def scan_cove_directory(self, directory_path):
        """Scans a directory for playable audio files and returns structured objects."""
        supported_extensions = ('.mp3', '.flac', '.ogg', '.m4a', '.wav', '.opus', '.mp4', '.mkv')
        tracks = []

        try:
            for entry in os.scandir(directory_path):
                if entry.is_file() and entry.name.lower().endswith(supported_extensions):
                    metadata_string = self.get_track_metadata(entry.path)
                    tracks.append({
                        "path": entry.path,
                        "display": metadata_string
                    })
        except Exception:
            pass

        return sorted(tracks, key=lambda x: x["display"])

    # ==========================================
    # JSON PLAYLIST STORAGE
    # ==========================================

    def save_playlist_json(self, name: str, tracks: list[dict]) -> bool:
        """Save playlist as JSON with full metadata."""
        playlist_path = PLAYLIST_DIR / f"{name}.json"
        try:
            data = {
                "name": name,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tracks": tracks
            }
            with open(playlist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError:
            return False

    def load_playlist_json(self, name: str) -> list[dict]:
        """Load JSON playlist, return track list with metadata (drops missing files)."""
        playlist_path = PLAYLIST_DIR / f"{name}.json"
        if not playlist_path.exists():
            return []
        try:
            with open(playlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("tracks", [])
            return [t for t in tracks if os.path.exists(t.get("path", ""))]
        except (IOError, json.JSONDecodeError):
            return []

    def get_available_playlists_json(self) -> list[str]:
        """List JSON playlists."""
        if not PLAYLIST_DIR.exists():
            return []
        return [f.stem for f in PLAYLIST_DIR.glob("*.json")]

    def delete_playlist(self, name: str) -> bool:
        """Delete playlist files (cleans up legacy .m3u too)."""
        deleted = False
        for ext in (".json", ".m3u"):
            p = PLAYLIST_DIR / f"{name}{ext}"
            if p.exists():
                p.unlink()
                deleted = True
        return deleted

    # ==========================================
    # IPC MPV SOCKET COMMUNICATIONS
    # ==========================================

    def _send_mpv_command(self, command_list):
        """Sends a JSON IPC command payload string to the background MPV socket instance."""
        try:
            if not self.client:
                if not os.path.exists(self.socket_path):
                    try:
                        subprocess.Popen(
                            ["mpv", "--idle=yes", f"--input-ipc-server={self.socket_path}", "--no-video"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        time.sleep(0.3)
                    except Exception:
                        pass
                self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.client.connect(self.socket_path)

            payload = json.dumps({"command": command_list}) + "\n"
            self.client.sendall(payload.encode("utf-8"))
            self.client.recv(1024)
            return True
        except (socket.error, Exception):
            self.client = None
            # Retry once with a fresh socket connection after attempting to spawn mpv if missing
            try:
                if not os.path.exists(self.socket_path):
                    subprocess.Popen(
                        ["mpv", "--idle=yes", f"--input-ipc-server={self.socket_path}", "--no-video"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    time.sleep(0.4)
                self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.client.connect(self.socket_path)
                payload = json.dumps({"command": command_list}) + "\n"
                self.client.sendall(payload.encode("utf-8"))
                self.client.recv(1024)
                return True
            except Exception:
                self.client = None
                return False


# ==========================================
# CLI MODULE-LEVEL HELPERS
# ==========================================

_global_player = SirenPlayer(socket_path="/tmp/siren-mpv.sock")

_META_CACHE: dict = {}
_META_CACHE_MAX = 8000

_queue_driven = False
_last_played_label = ""


def _mpv_get(prop, default=None):
    """Fetch a single mpv property via a fresh, short-lived socket connection."""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.5)
        client.connect(_global_player.socket_path)
        client.sendall((json.dumps({"command": ["get_property", prop]}) + "\n").encode())
        raw = client.recv(4096).decode()
        client.close()
        for line in raw.splitlines():
            try:
                res = json.loads(line)
                if res.get("error") == "success" and "data" in res:
                    return res["data"]
            except Exception:
                continue
    except Exception:
        pass
    return default


def get_prop(prop, default=None):
    """Public property getter (used by the TUI)."""
    return _mpv_get(prop, default)


def scan_library():
    music_path = Path(os.path.expanduser("~/Music"))
    if not music_path.exists():
        return []
    files = []
    for root, _, filenames in os.walk(music_path):
        for f in filenames:
            if f.lower().endswith(AUDIO_EXT):
                files.append(Path(root) / f)
    return sorted(files)


def resolve_play_args(targets):
    lib = scan_library()
    if not targets:
        return [str(p) for p in lib]
    matched = []
    query = " ".join(targets).lower()
    for p in lib:
        if query in str(p).lower():
            matched.append(str(p))
    return matched if matched else [str(p) for p in lib]


def start_playlist(files, shuffle=True):
    global _queue_driven, _last_played_label
    if not files:
        print("No tracks found to play.")
        return 1
    if shuffle:
        random.shuffle(files)

    if not os.path.exists(_global_player.socket_path):
        try:
            subprocess.Popen(
                ["mpv", "--idle=yes", f"--input-ipc-server={_global_player.socket_path}", "--no-video", "--audio-display=no"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            time.sleep(0.4)
        except Exception:
            pass

    _global_player._send_mpv_command(["playlist-clear"])
    _global_player._send_mpv_command(["loadfile", files[0], "replace"])
    _global_player._send_mpv_command(["set_property", "pause", False])
    _global_player._send_mpv_command(["set_property", "video", "no"])

    for f in files[1:]:
        _global_player._send_mpv_command(["loadfile", f, "append"])

    _queue_driven = False
    _last_played_label = _global_player.get_track_metadata(files[0])
    print(f"Playing queue ({len(files)} tracks)")
    return 0


def _now_playing_path() -> str:
    path = _mpv_get("path", "")
    if path and path.startswith("file://"):
        path = path[7:]
    return path


# ==========================================
# QUEUE-DRIVEN PLAYBACK
# The queue is the source of truth. When playing from the queue we mirror it
# into mpv's playlist so a track ending naturally advances to the next item.
# ==========================================

def _sync_mpv_playlist(paths: list[str]) -> bool:
    """Replace mpv's playlist with the given paths (first plays immediately)."""
    if not paths:
        _global_player._send_mpv_command(["stop"])
        return True
    if not _global_player._send_mpv_command(["playlist-clear"]):
        return False
    _global_player._send_mpv_command(["loadfile", paths[0], "replace"])
    for p in paths[1:]:
        _global_player._send_mpv_command(["loadfile", p, "append"])
    _global_player._send_mpv_command(["set_property", "pause", False])
    _global_player._send_mpv_command(["set_property", "video", "no"])
    return True


def play_queue_from(index: int = 0, wrap: bool = False) -> bool:
    """Start playback from a queue index, mirroring the queue into mpv.
    If wrap=True the queue loops around for explicit next/prev; otherwise the
    queue simply ends when the last mirrored track finishes."""
    global _queue_driven, _last_played_label
    items = queue.list()
    if not items or not (0 <= index < len(items)):
        return False
    ordered = (items[index:] + items[:index]) if wrap else items[index:]
    paths = [it["path"] for it in ordered]
    if not _sync_mpv_playlist(paths):
        return False
    _queue_driven = True
    if ordered:
        _last_played_label = ordered[0].get("display") or ""
    return True


def queue_add_and_play(path: str, prepend: bool = False) -> bool:
    """Add a track to the queue (if absent) and start playing it."""
    path = os.path.expanduser(path)
    items = queue.list()
    idx = next((i for i, it in enumerate(items) if it.get("path") == path), -1)
    if idx < 0:
        queue_add(path, prepend=prepend)
        items = queue.list()
        idx = next((i for i, it in enumerate(items) if it.get("path") == path), 0)
    return play_queue_from(idx, wrap=False)


def _maybe_resync_queue() -> None:
    """Rebuild mpv's playlist from the queue when queue-driven. Preserves the
    currently playing position when the current track is still queued."""
    global _queue_driven
    if not _queue_driven:
        return
    items = queue.list()
    if not items:
        _queue_driven = False
        _global_player._send_mpv_command(["playlist-clear"])
        _global_player._send_mpv_command(["stop"])
        return
    cur = _now_playing_path()
    idx = 0
    for i, it in enumerate(items):
        if it.get("path") == cur:
            idx = i
            break
    _sync_mpv_playlist([it["path"] for it in items])
    if idx > 0:
        _global_player._send_mpv_command(["set_property", "playlist-pos", idx])


def queue_resync() -> None:
    _maybe_resync_queue()


def cmd_next():
    """Advance playback. If the current track is in the siren queue, play the
    next queued item (wrapping); otherwise fall back to mpv's own playlist."""
    cur = _now_playing_path()
    items = queue.list()
    if items and cur:
        for i, item in enumerate(items):
            if item.get("path") == cur:
                play_queue_from((i + 1) % len(items), wrap=True)
                return 0
    _global_player._send_mpv_command(["playlist-next"])
    return 0


def cmd_prev():
    """Go back a track. Prefers the siren queue, falls back to mpv playlist."""
    cur = _now_playing_path()
    items = queue.list()
    if items and cur:
        for i, item in enumerate(items):
            if item.get("path") == cur:
                play_queue_from((i - 1) % len(items), wrap=True)
                return 0
    _global_player._send_mpv_command(["playlist-prev"])
    return 0


def cmd_stop():
    global _queue_driven, _last_played_label
    _queue_driven = False
    _last_played_label = ""
    _global_player._send_mpv_command(["stop"])
    return 0


def cmd_now():
    now = now_label()
    if now:
        print(now)
    else:
        print("Not playing")
    return 0


def cmd_pause():
    _global_player._send_mpv_command(["cycle", "pause"])
    return 0


def now_label():
    path = _mpv_get("path")
    if path:
        if path.startswith("file://"):
            path = path[7:]
        return _global_player.get_track_metadata(path)
    return _last_played_label


def time_pair():
    pos = _mpv_get("time-pos") or 0.0
    dur = _mpv_get("duration") or 0.0
    return float(pos), float(dur)


def sock_alive():
    return os.path.exists(_global_player.socket_path)


def is_paused():
    return bool(_mpv_get("pause", False))


def get_playlist_count():
    return int(_mpv_get("playlist-count", 0) or 0)


# ==========================================
# REPEAT MODES
# ==========================================

def get_repeat() -> str:
    """Return current repeat mode: 'off', 'all', or 'track'."""
    loop_playlist = _mpv_get("loop-playlist")
    loop_file = _mpv_get("loop-file")
    if loop_playlist in ("inf", "yes", "always", True):
        return "all"
    if loop_file in ("inf", "yes", "always", True):
        return "track"
    return "off"


def cycle_repeat() -> str:
    """Cycle repeat off -> all -> track -> off. Returns the new mode."""
    nxt = {"off": "all", "all": "track", "track": "off"}[get_repeat()]
    loop_all = "inf" if nxt == "all" else "no"
    loop_track = "inf" if nxt == "track" else "no"
    _global_player._send_mpv_command(["set_property", "loop-playlist", loop_all])
    _global_player._send_mpv_command(["set_property", "loop-file", loop_track])
    return nxt


def play_playlist(name: str) -> bool:
    """Load a saved playlist into the queue and start playing it."""
    tracks = _global_player.load_playlist_json(name)
    if not tracks:
        return False
    queue.items = tracks
    return play_queue_from(0, wrap=False)


# ==========================================
# MODULE-LEVEL QUEUE & PLAYLIST HELPERS
# ==========================================

queue = Queue()


def queue_add(path: str, prepend: bool = False) -> int:
    n = queue.add(path, _global_player, prepend)
    if prepend:
        _maybe_resync_queue()
    elif _queue_driven:
        _global_player._send_mpv_command(["loadfile", os.path.expanduser(path), "append"])
    return n


def queue_add_multiple(paths: list[str], prepend: bool = False) -> int:
    n = queue.add_multiple(paths, _global_player, prepend)
    if _queue_driven:
        _maybe_resync_queue()
    return n


def queue_remove(index: int) -> dict | None:
    item = queue.remove(index)
    if item is not None:
        _maybe_resync_queue()
    return item


def queue_move(from_idx: int, to_idx: int) -> bool:
    moved = queue.move(from_idx, to_idx)
    if moved:
        _maybe_resync_queue()
    return moved


def queue_clear():
    queue.clear()
    _maybe_resync_queue()


def queue_list() -> list[dict]:
    return queue.list()


def queue_validate() -> list[dict]:
    removed = queue.validate_all(_global_player)
    if removed:
        _maybe_resync_queue()
    return removed


def save_playlist_json(name: str, tracks: list[dict] = None) -> bool:
    if tracks is None:
        tracks = queue.list()
    return _global_player.save_playlist_json(name, tracks)


def load_playlist_json(name: str) -> list[dict]:
    tracks = _global_player.load_playlist_json(name)
    if tracks:
        queue.items = tracks
        _maybe_resync_queue()
    return tracks


def list_playlists_json() -> list[str]:
    return _global_player.get_available_playlists_json()


def delete_playlist(name: str) -> bool:
    return _global_player.delete_playlist(name)


def find_playlist(name: str) -> str | None:
    """Match a playlist by exact (case-insensitive) name, else by unique prefix."""
    names = _global_player.get_available_playlists_json()
    low = name.lower()
    exact = next((n for n in names if n.lower() == low), None)
    if exact:
        return exact
    matches = [n for n in names if n.lower().startswith(low)]
    return matches[0] if len(matches) == 1 else None
