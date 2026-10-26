"""macOS: read Spotify and Apple Music through `osascript` (JavaScript for Automation).

Why only these two? Since macOS 15.4 the system-wide "now playing" API
(MediaRemote) is limited to entitled Apple binaries, so browsers cannot be read.
Players that expose an AppleScript dictionary can still be asked directly.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from collections.abc import Callable

from ..models import PlaybackState, TrackInfo
from .base import MediaWatcher

log = logging.getLogger(__name__)

# Spotify reports `duration` in milliseconds, Music in seconds.
DURATION_DIVISOR = {"Spotify": 1000, "Music": 1}
SCRIPT_TIMEOUT_SECONDS = 3
# errAEEventNotPermitted, formatted the way osascript prints it on stderr.
AUTOMATION_DENIED_ERROR = "(-1743)"
AUTOMATION_HINT = ("macOS blocked access to Spotify/Music. Allow it in System Settings → "
                   "Privacy & Security → Automation: enable Spotify and Music under the app "
                   "LyricPiP was started from (Terminal, iTerm, VS Code…).")

# JXA, not AppleScript: `tell application "Spotify"` resolves at compile time and
# shows a "Where is Spotify?" dialog when it is not installed, whereas
# `Application(name)` throws a catchable error. `running()` never launches the app.
# Automation denial is rethrown so osascript exits non-zero and Python can say so.
SCRIPT = """
function read(name) {
  let app;
  try { app = Application(name); } catch (e) { return null; }   // not installed
  if (!app.running()) return null;                               // closed: never launch
  try {
    const t = app.currentTrack;
    return { player: name, state: app.playerState(), title: t.name(), artist: t.artist(),
             album: t.album(), duration: t.duration(), position: app.playerPosition() };
  } catch (e) {
    if (e.errorNumber === -1743) throw e;                        // Automation denied
    return null;                                                 // stopped, no track
  }
}
JSON.stringify(["Spotify", "Music"].map(read).filter(Boolean));
"""


class MacOSAppleScriptWatcher(MediaWatcher):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._logged_once: set[str] = set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._publish(self._poll())
            except Exception:
                log.exception("osascript poll failed")
                self._publish(PlaybackState())
            self._stop_event.wait(self.interval)

    def _poll(self) -> PlaybackState:
        try:
            raw = self._run_script()
        except FileNotFoundError:
            self._log_once("`osascript` not found; it ships with macOS in /usr/bin")
            return PlaybackState()
        except subprocess.TimeoutExpired:
            log.warning("osascript timed out after %ss (is an Automation prompt waiting?)",
                        SCRIPT_TIMEOUT_SECONDS)
            return PlaybackState()
        except subprocess.CalledProcessError as e:
            self._log_script_error(e.stderr)
            return PlaybackState()
        return parse_players(raw, self._ignored)

    def _run_script(self) -> str:
        # osascript writes UTF-8 whatever the locale; decode it as such for non-Latin titles.
        return subprocess.run(["osascript", "-l", "JavaScript", "-e", SCRIPT],
                              capture_output=True, encoding="utf-8", check=True,
                              timeout=SCRIPT_TIMEOUT_SECONDS).stdout

    def _log_script_error(self, stderr: str) -> None:
        if AUTOMATION_DENIED_ERROR in stderr:
            self._log_once(AUTOMATION_HINT)
        else:
            log.warning("osascript failed: %s", stderr.strip())

    def _log_once(self, message: str) -> None:
        # Setup problems recur on every poll; repeating them would bury every other log line.
        if message not in self._logged_once:
            self._logged_once.add(message)
            log.error(message)


def parse_players(raw: str, is_ignored: Callable[[str], bool]) -> PlaybackState:
    """Turn the script's JSON list of player snapshots into the one state to show."""
    try:
        snapshots = json.loads(raw)
    except ValueError:
        log.warning("osascript returned invalid JSON: %r", raw[:200])
        return PlaybackState()
    candidates = [s for s in snapshots if s.get("title") and not is_ignored(s["player"])]
    if not candidates:
        return PlaybackState()
    return _to_playback_state(_prefer_playing(candidates))


def _prefer_playing(candidates: list[dict]) -> dict:
    # Falls back to script order, so a paused Spotify beats a paused Music.
    return next((c for c in candidates if c["state"] == "playing"), candidates[0])


def _to_playback_state(snapshot: dict) -> PlaybackState:
    player = snapshot["player"]
    duration = snapshot.get("duration")
    track = TrackInfo(
        title=snapshot["title"],
        artist=snapshot.get("artist") or "",
        album=snapshot.get("album") or "",
        duration=duration / DURATION_DIVISOR[player] if duration else None,
        player=player,
    )
    position = float(snapshot.get("position") or 0.0)
    return PlaybackState(track, snapshot["state"] == "playing", position, time.monotonic())
