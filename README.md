# LyricPiP — floating synced lyrics for whatever you're playing

A small always-on-top, transparent "picture-in-picture" window that detects the
song currently playing on your computer (Spotify, YouTube in a browser, VLC, …),
fetches **time-synced lyrics**, highlights the current line, and optionally shows
**romanization** (romaji / pinyin / Korean RR / Cyrillic, Greek, Arabic … → Latin)
under non-Latin lines.

* Move it by dragging; resize by dragging any edge or corner.
* Translucent background, so what's behind it stays visible.
* Windows 10/11, Ubuntu (22.04+) and macOS 13+ — Python 3.10+.

> **MVP status:** the parsing, matching, provider and romanization logic is unit-tested
> and smoke-tested. The OS-specific parts (Windows SMTC, Linux `playerctl`, macOS `osascript`, the Qt window)
> must be verified on your machines — see *Troubleshooting*.

---

## 1. Tech stack (and why)

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.10+ | Best romanization libraries, fast iteration |
| GUI | PySide6 (Qt 6) | Frameless/translucent/always-on-top windows on Windows + Linux; OS-native move/resize |
| Now-playing (Windows) | SMTC via `winrt-*` packages | One API covers Spotify, browsers, VLC, Apple Music… |
| Now-playing (Linux) | MPRIS via `playerctl` | Every mainstream Linux player/browser exposes MPRIS |
| Now-playing (macOS) | JXA via built-in `osascript` | No extra dependency; asks Spotify and Apple Music directly, never launches them |
| HTTP | `requests` (+ `beautifulsoup4` for Genius) | Simple, robust |
| Romanization | `pykakasi`, `pypinyin`, `korean-romanizer`, `unidecode` | JA / ZH / KO / everything else |

## 2. Architecture

```text
 OS media API ──► MediaWatcher thread ──► PlaybackState (title, artist, position…)
 (SMTC/MPRIS/JXA)                               │ polled 10×/s
                                                ▼
                      Overlay (Qt UI) ◄── LyricsResult ◄── LyricsManager
                       picks current line        │   cache → providers (parallel) → LRC parse → romanize
                       renders HTML               ▼
                                     LRCLIB · NetEase · KuGou · lyrics.ovh · Genius · (LyricsTranslate stub)
```

```text
lyricpip/
  app.py              entry point (wiring)
  config.py           JSON settings
  models.py           dataclasses (TrackInfo, PlaybackState, LyricLine …)
  textutil.py         cleans "(Official Video)", "feat.", "Artist - Title" metadata
  romanize.py         script detection + romanization
  media/              windows_smtc.py · linux_mpris.py · macos_applescript.py · base.py
  lyrics/             manager.py · lrc.py · matching.py · cache.py
  lyrics/providers/   lrclib · netease · kugou · ovh · genius · lyricstranslate(stub)
  ui/overlay.py       the floating window
tests/test_core.py    stdlib-only unit tests
```

## 3. Setup

### Ubuntu (22.04 / 24.04)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip playerctl \
                    libxcb-cursor0 libxkbcommon-x11-0 libegl1

cd LyricPiP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m lyricpip
```

Shortcut: `./run.sh` does the venv + install + launch for you.

### Windows 10/11

1. Install Python 3.10+ from python.org (tick **Add python.exe to PATH**).
2. In PowerShell:

```powershell
cd LyricPiP
py -3 -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m lyricpip
```

Shortcut: double-click `run.bat`.

### macOS 13+

Detects **Spotify** and **Apple Music** only. Browsers (YouTube, YouTube Music) are not supported:
since macOS 15.4 the system-wide "now playing" API (MediaRemote) is restricted to entitled Apple
binaries, so there is no supported way for a third-party app to read browser playback.

1. Install Python 3.10+ from python.org or with `brew install python`
   (the `python3` bundled with the Xcode Command Line Tools is 3.9, too old).
2. In Terminal:

```bash
cd LyricPiP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m lyricpip
```

Shortcut: `./run.sh` does the venv + install + launch for you.

**One-time Automation prompt.** The first time Spotify or Music is running, macOS asks
*"Terminal" wants access to control "Spotify"* (named after the app you started LyricPiP from:
Terminal, iTerm, VS Code…). Allow it. If you declined, the log says so; turn it back on in
**System Settings → Privacy & Security → Automation** by enabling Spotify and Music under that app.

LyricPiP only talks to players that are already running: it never launches Spotify or Music,
and an app that isn't installed is skipped without a dialog.

### Try it

Start playing something (Spotify, or a YouTube Music tab in Firefox/Chrome; on macOS Spotify or Music),
then launch the app.
The window shows *Searching lyrics…* and then the synced lyrics.

## 4. Using it

| Action | How |
| --- | --- |
| Move | Drag the window body |
| Resize | Drag any edge or corner |
| Settings menu | Right-click |
| Toggle romanization | Right-click → *Show romanization* |
| Font size | Ctrl + mouse wheel, or menu |
| Background opacity | Menu → *Background opacity* |
| Lyrics too early/late | `]` = show sooner, `[` = show later (±0.5 s, window must be focused) or menu |
| Scroll unsynced lyrics | Mouse wheel |
| Wrong lyrics? | Right-click → *Re-fetch lyrics* |
| Quit | Right-click → *Quit* |

Settings and window position are saved to
`~/.config/LyricPiP/config.json` (Linux), `~/Library/Application Support/LyricPiP/config.json` (macOS)
or `%LOCALAPPDATA%\LyricPiP\config.json` (Windows).
Lyrics are cached in `~/.cache/LyricPiP/lyrics/` (Linux) / `~/Library/Caches/LyricPiP/lyrics/` (macOS) /
`%LOCALAPPDATA%\LyricPiP\Cache\lyrics\` (Windows).

### config.json options

```json
{
  "providers": ["lrclib", "netease", "kugou", "ovh", "genius"],
  "genius_token": "",
  "ignore_players": ["chromium"],
  "font_size": 22,
  "bg_alpha": 150,
  "show_romanization": true,
  "offset": 0.0
}
```

`providers` order is the priority order. Synced lyrics from any provider always beat plain text.

## 5. Lyric sources

| Provider | Type | Key needed | Notes |
| --- | --- | --- | --- |
| LRCLIB | synced + plain | no | Best open source; first choice |
| NetEase | synced | no | Great for C/J/K-pop; unofficial endpoints, may be rate/geo limited |
| KuGou | synced | no | Unofficial endpoints, 3-step flow |
| lyrics.ovh | plain | no | Fallback |
| Genius | plain | **free token** | Set `GENIUS_TOKEN` env var or `genius_token`; page scraping is fragile |
| LyricsTranslate | — | — | **Stub, disabled.** No public API, Cloudflare-protected, translations are un-timed, scraping restricted by ToS |

Add a source: copy `lyrics/providers/ovh.py`, implement `fetch`, register it in `providers/__init__.py`.

## 6. Romanization

* Japanese (kana present) → Hepburn romaji (`pykakasi`)
* Chinese (Han only) → Pinyin with tone marks (`pypinyin`)
* Korean → Revised Romanization (`korean-romanizer`)
* Cyrillic, Greek, Arabic, Hebrew, Thai, Devanagari… → approximate via `unidecode`
  (good enough to read along; not linguistically exact — Thai/Arabic especially)
* Kanji-only Japanese lines are recognised via a song-level language hint.

## 7. Troubleshooting

* **"Nothing playing" on Ubuntu** – run `playerctl status`. If it errors, your player has no MPRIS support
  (for Firefox keep the tab playing; for Chrome enable *chrome://flags → Hardware media key handling*).
* **"Nothing playing" on macOS** – only Spotify and Music are detected (not browsers). If the log mentions
  Automation, enable Spotify and Music under your terminal app in *System Settings → Privacy & Security → Automation*.
* **Window not on top / odd on Ubuntu Wayland** – the app forces XWayland (`QT_QPA_PLATFORM=xcb`) because
  GNOME ignores always-on-top for native Wayland windows. If Qt can't start, make sure `libxcb-cursor0` is installed.
* **Lyrics slightly off in browsers (Windows)** – some browsers report timeline positions sloppily; nudge with `[` / `]`.
* **Wrong song matched** – titles from YouTube are messy; use *Re-fetch*, or play from a music app.
* **Windows: `winrt` import error** – `pip install -r requirements.txt` inside the venv; Python 3.9+ required.
* **Logs** – run from a terminal; each provider logs `hit` / `miss` / `failed`.

## 8. Tests

```bash
python -m unittest discover -s tests -v
```

## 9. Packaging (optional)

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name LyricPiP --collect-all pykakasi --collect-all pypinyin lyricpip/__main__.py
```

(For Windows also add `--collect-all winrt`-style flags if modules are reported missing.)

## 10. Roadmap

* System-tray icon, global hotkeys, click-through "lock" mode
* Karaoke word-level highlighting (enhanced LRC / NetEase `yrc`)
* Translation line (NetEase `tlyric`), manual lyric search dialog
* Push-based Linux D-Bus listener (`dbus-next`) instead of polling

## 11. Legal

Lyrics are copyrighted. This tool fetches them on demand for personal display and caches them locally;
it does not redistribute them. NetEase/KuGou endpoints are unofficial and may change or violate their
terms — use at your own discretion and keep request rates low.
