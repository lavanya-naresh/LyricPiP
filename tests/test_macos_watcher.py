"""macOS watcher tests. No osascript, no thread start, so they run on any OS."""

import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from lyricpip.media import create_watcher
from lyricpip.media.macos_applescript import MacOSAppleScriptWatcher, parse_players

LOGGER = "lyricpip.media.macos_applescript"
OSASCRIPT_RUN = "lyricpip.media.macos_applescript.subprocess.run"
AUTOMATION_DENIED_STDERR = ("execution error: Error: Error: Not authorized to send "
                            "Apple events to Spotify. (-1743)")

# Real script output captured from Music.app (durations in seconds).
MUSIC = {"player": "Music", "state": "paused", "title": "Bad Luck", "artist": "Adam Jensen",
         "album": "Bad Luck - Single", "duration": 202.3699951171875,
         "position": 2.6040000915527344}
# Spotify's dictionary reports duration in milliseconds, position in seconds.
SPOTIFY = {"player": "Spotify", "state": "playing", "title": "Bohemian Rhapsody",
           "artist": "Queen", "album": "A Night at the Opera", "duration": 354320,
           "position": 12.5}


def nothing_ignored(player: str) -> bool:
    return False


def parse(*snapshots, is_ignored=nothing_ignored):
    return parse_players(json.dumps(list(snapshots)), is_ignored)


class ParsePlayersTests(unittest.TestCase):
    def test_snapshot_becomes_track_and_position(self):
        state = parse(SPOTIFY)
        track = state.track
        self.assertEqual(
            (track.title, track.artist, track.album, track.player),
            ("Bohemian Rhapsody", "Queen", "A Night at the Opera", "Spotify"),
        )
        self.assertEqual((state.playing, state.position), (True, 12.5))

    def test_spotify_duration_milliseconds_become_seconds(self):
        self.assertAlmostEqual(parse(SPOTIFY).track.duration, 354.32)

    def test_music_duration_stays_in_seconds(self):
        self.assertAlmostEqual(parse(MUSIC).track.duration, 202.3699951171875)

    def test_missing_duration_is_unknown(self):
        no_duration = {k: v for k, v in MUSIC.items() if k != "duration"}
        self.assertIsNone(parse(no_duration).track.duration)

    def test_playing_player_beats_paused_one(self):
        state = parse({**SPOTIFY, "state": "paused"}, {**MUSIC, "state": "playing"})
        self.assertEqual(state.track.player, "Music")

    def test_script_order_breaks_tie_when_nothing_plays(self):
        state = parse({**SPOTIFY, "state": "paused"}, MUSIC)
        self.assertEqual(state.track.player, "Spotify")

    def test_ignored_player_is_skipped(self):
        state = parse(SPOTIFY, MUSIC, is_ignored=lambda player: player == "Spotify")
        self.assertEqual(state.track.player, "Music")

    def test_snapshot_without_title_is_skipped(self):
        state = parse({**SPOTIFY, "title": ""}, MUSIC)
        self.assertEqual(state.track.player, "Music")

    def test_no_running_player_gives_empty_state(self):
        state = parse()
        self.assertEqual((state.track, state.playing), (None, False))

    def test_invalid_json_gives_empty_state_and_logs(self):
        with self.assertLogs("lyricpip.media.macos_applescript", "WARNING"):
            state = parse_players("execution error", nothing_ignored)
        self.assertIsNone(state.track)


def osascript_exit(code: int, stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(code, ["osascript"], output="", stderr=stderr)


class WatcherPollTests(unittest.TestCase):
    def setUp(self):
        self.watcher = MacOSAppleScriptWatcher()

    def test_script_output_is_parsed(self):
        finished = subprocess.CompletedProcess(["osascript"], 0, json.dumps([MUSIC]), "")
        with mock.patch(OSASCRIPT_RUN, return_value=finished):
            self.assertEqual(self.watcher._poll().track.title, "Bad Luck")

    def test_missing_osascript_gives_empty_state_and_logs(self):
        with mock.patch(OSASCRIPT_RUN, side_effect=FileNotFoundError), self.assertLogs(LOGGER):
            state = self.watcher._poll()
        self.assertIsNone(state.track)

    def test_timeout_gives_empty_state_and_logs(self):
        timeout = subprocess.TimeoutExpired(["osascript"], 3)
        with mock.patch(OSASCRIPT_RUN, side_effect=timeout), self.assertLogs(LOGGER):
            state = self.watcher._poll()
        self.assertIsNone(state.track)

    def test_script_error_gives_empty_state_and_logs_stderr(self):
        failure = osascript_exit(1, "execution error: Error: boom (-2700)")
        with mock.patch(OSASCRIPT_RUN, side_effect=failure), self.assertLogs(LOGGER) as logs:
            state = self.watcher._poll()
        self.assertIsNone(state.track)
        self.assertIn("boom", logs.output[0])

    def test_automation_denied_logs_settings_hint_once(self):
        denied = osascript_exit(1, AUTOMATION_DENIED_STDERR)
        with mock.patch(OSASCRIPT_RUN, side_effect=denied), self.assertLogs(LOGGER) as logs:
            self.watcher._poll()
            self.watcher._poll()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("Privacy & Security", logs.output[0])


class WatcherLoopTests(unittest.TestCase):
    def test_failed_poll_replaces_stale_track_with_empty_state(self):
        watcher = MacOSAppleScriptWatcher()
        watcher._publish(parse(SPOTIFY))

        def fail_and_stop():
            watcher.stop()
            raise RuntimeError("unexpected")

        with mock.patch.object(watcher, "_poll", side_effect=fail_and_stop), \
                self.assertLogs(LOGGER):
            watcher.run()
        self.assertIsNone(watcher.get_state().track)


class WatcherFactoryTests(unittest.TestCase):
    def test_darwin_gets_applescript_watcher_polling_every_second(self):
        with mock.patch.object(sys, "platform", "darwin"):
            watcher = create_watcher()
        self.assertIsInstance(watcher, MacOSAppleScriptWatcher)
        self.assertEqual(watcher.interval, 1.0)

    def test_unsupported_platform_error_lists_supported_systems(self):
        with mock.patch.object(sys, "platform", "sunos5"), \
                self.assertRaisesRegex(RuntimeError, "Windows, Linux and macOS"):
            create_watcher()


if __name__ == "__main__":
    unittest.main()
