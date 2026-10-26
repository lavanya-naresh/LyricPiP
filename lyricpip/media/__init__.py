"""Factory choosing the right watcher for the current OS."""
import sys

from .base import MediaWatcher


def create_watcher(**kwargs) -> MediaWatcher:
    if sys.platform == "win32":
        from .windows_smtc import WindowsSMTCWatcher
        return WindowsSMTCWatcher(interval=0.5, **kwargs)
    if sys.platform.startswith("linux"):
        from .linux_mpris import LinuxMPRISWatcher
        return LinuxMPRISWatcher(interval=1.0, **kwargs)
    if sys.platform == "darwin":
        from .macos_applescript import MacOSAppleScriptWatcher
        return MacOSAppleScriptWatcher(interval=1.0, **kwargs)
    raise RuntimeError(f"Unsupported platform: {sys.platform} (Windows, Linux and macOS only)")
