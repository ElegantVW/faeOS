#!/usr/bin/env python3
"""fae_ambience — per-app ambient music that never steals Siren's mpv.

Each app gets its own mpv process + unix IPC socket under /tmp/fae-ambience-*.sock.
PipeWire/Pulse mixes this with siren, paplay, fairy-lantern, etc. We never
touch /tmp/siren-mpv.sock and never kill foreign mpv processes.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

# Defaults: original faeOS chiptune pack (not game rips).
MUSIC_ROOT = Path.home() / "Music" / "faeos-chiptune"
TRACKS = {
    # Full ~3:00 waltz arc (*Glass Fog*); mpv loops the whole piece (game design).
    "murmur": MUSIC_ROOT / "murmur_glass_fog.wav",
    "scroll": MUSIC_ROOT / "route_calm_town.wav",
}

# Soft background — leaves headroom for UI blips / siren / games.
DEFAULT_VOLUME = 38
SOCK_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))


def _disabled() -> bool:
    v = os.environ.get("FAE_AMBIENCE", "1").strip().lower()
    return v in ("0", "false", "no", "off", "quiet")


def _sock_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return SOCK_DIR / f"fae-ambience-{safe}.sock"


class Ambience:
    """Own-process ambient player for one app name."""

    def __init__(
        self,
        name: str,
        track: Path | str | None = None,
        *,
        volume: int = DEFAULT_VOLUME,
        loop: bool = True,
    ) -> None:
        self.name = name
        self.track = Path(track) if track else TRACKS.get(name, Path())
        self.volume = max(0, min(100, int(volume)))
        self.loop = loop
        self.sock = _sock_path(name)
        self._proc: subprocess.Popen | None = None
        self._owned = False  # True if this object started the process

    # ── IPC ────────────────────────────────────────────────────────────

    def _alive_sock(self) -> bool:
        return self.sock.is_socket() or self.sock.exists()

    def _send(self, cmd: list, *, timeout: float = 0.4) -> dict | None:
        if not self._alive_sock():
            return None
        c = None
        try:
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.settimeout(timeout)
            c.connect(str(self.sock))
            c.sendall((json.dumps({"command": cmd}) + "\n").encode("utf-8"))
            data = b""
            while b"\n" not in data:
                chunk = c.recv(4096)
                if not chunk:
                    break
                data += chunk
            for line in data.decode("utf-8", errors="replace").splitlines():
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        except (OSError, ValueError, socket.timeout):
            return None
        finally:
            if c is not None:
                try:
                    c.close()
                except OSError:
                    pass
        return None

    def _get(self, prop: str, default=None):
        res = self._send(["get_property", prop])
        if res and res.get("error") == "success" and "data" in res:
            return res["data"]
        return default

    def _proc_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self, *, paused: bool = False) -> bool:
        """Start dedicated mpv if needed; load our track. Does not touch Siren."""
        if _disabled():
            return False
        if not self.track.is_file():
            return False

        if self._alive_sock() and self._send(["get_property", "pause"]) is not None:
            # Existing instance for this app — retarget track + volume.
            self._send(["loadfile", str(self.track), "replace"])
            self._send(["set_property", "volume", self.volume])
            self._send(["set_property", "loop-file", "inf" if self.loop else "no"])
            self._send(["set_property", "pause", bool(paused)])
            return True

        # Stale socket without a live server
        try:
            if self.sock.exists():
                self.sock.unlink()
        except OSError:
            pass

        args = [
            "mpv",
            "--no-video",
            "--audio-display=no",
            "--really-quiet",
            "--no-terminal",
            f"--volume={self.volume}",
            f"--input-ipc-server={self.sock}",
            # Share the default audio device; never exclusive / never jack-only.
            "--ao=pulse,pipewire,alsa",
            # Soft start so we don't punch over other programs.
            "--audio-stream-silence=yes",
        ]
        if self.loop:
            args.append("--loop-file=inf")
        if paused:
            args.append("--pause")
        args.append(str(self.track))

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # detach; we quit via IPC, not group kill
            )
        except FileNotFoundError:
            self._proc = None
            return False
        except OSError:
            self._proc = None
            return False

        self._owned = True
        for _ in range(30):
            if self._alive_sock() and self._send(["get_property", "pause"]) is not None:
                return True
            if self._proc.poll() is not None:
                break
            time.sleep(0.05)
        return self._alive_sock()

    def pause(self) -> bool:
        return bool(self._send(["set_property", "pause", True]))

    def resume(self) -> bool:
        if not self._alive_sock():
            return self.start(paused=False)
        return bool(self._send(["set_property", "pause", False]))

    def toggle(self) -> str:
        """Play/pause toggle. Returns playing | paused | off."""
        if _disabled():
            return "off"
        if not self.track.is_file():
            return "off"
        if not self._alive_sock() or self._send(["get_property", "pause"]) is None:
            ok = self.start(paused=False)
            return "playing" if ok else "off"
        paused = bool(self._get("pause", True))
        if paused:
            self._send(["set_property", "pause", False])
            return "playing"
        self._send(["set_property", "pause", True])
        return "paused"

    def status(self) -> str:
        """playing | paused | off"""
        if not self._alive_sock():
            return "off"
        res = self._send(["get_property", "pause"])
        if res is None:
            return "off"
        if res.get("error") != "success":
            return "off"
        return "paused" if res.get("data") else "playing"

    def stop(self) -> None:
        """Quit only this app's mpv; leave Siren and everything else alone."""
        if self._alive_sock():
            self._send(["quit"], timeout=0.3)
        # Brief wait for clean exit if we own the child
        if self._owned and self._proc is not None:
            try:
                self._proc.wait(timeout=0.6)
            except subprocess.TimeoutExpired:
                # Last resort: only our child, never killall/pgrep mpv
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=0.4)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
        self._proc = None
        self._owned = False
        try:
            if self.sock.exists():
                self.sock.unlink()
        except OSError:
            pass


def for_app(name: str, **kwargs) -> Ambience:
    return Ambience(name, TRACKS.get(name), **kwargs)
