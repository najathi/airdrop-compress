"""Entry point.

    python -m airdrop_compress            watch in the foreground (command line, like v1)
    python -m airdrop_compress gui        the menu bar app
    python -m airdrop_compress scan       convert files already in the AirDrop folder, then exit
    python -m airdrop_compress plugin validate <folder>
    python -m airdrop_compress settings   print the settings file location and contents

The packaged .app starts the menu bar app by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import signal
import sys
from pathlib import Path

from . import APP_NAME, __version__, paths


def setup_logging(to_file: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if to_file:
        paths.ensure_dirs()
        handlers = [logging.handlers.RotatingFileHandler(paths.LOG_FILE, maxBytes=2_000_000, backupCount=3)]
        if sys.stdout and sys.stdout.isatty():
            handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", handlers=handlers, force=True)
    for noisy in ("pdfminer", "PIL", "watchdog", "pywebview", "magika"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_watcher(scan_once: bool) -> int:
    from .engine import Engine
    from .plugins.manager import PluginManager
    from .settings import SettingsManager

    settings = SettingsManager()
    engine = Engine(settings, PluginManager(settings))

    def stop(_signum, _frame):
        engine.stop_event.set()

    signal.signal(signal.SIGTERM, stop)  # launchctl stop / bootout
    signal.signal(signal.SIGINT, stop)   # Ctrl+C
    if settings.current.general.paused and not scan_once:
        logging.info("Note: processing is paused in the app's settings; the command line ignores that.")
    return engine.run_blocking(scan_existing=scan_once, once=scan_once)


def validate_plugin(folder: Path) -> int:
    from .plugins.manager import load_manifest

    info = load_manifest(folder)
    if info.errors:
        print(f"✗ {folder}: not a valid plugin")
        for e in info.errors:
            print(f"  - {e}")
        return 1
    print(f"✓ {info.name} {info.version} ({info.id})")
    print(f"  handles {', '.join(info.file_types)} -> {', '.join(info.outputs)}")
    print(f"  permissions: {', '.join(info.permissions) or 'none'}")
    if info.incompatible:
        print(f"  ! not compatible with this version: {info.incompatible}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Internal: the sandboxed plugin host (see plugins/manager.py).
    if argv[:1] == ["--plugin-host"]:
        from .plugins import host
        return host.main()

    if paths.is_frozen():
        argv = [a for a in argv if not a.startswith("-psn")]  # old macOS process-serial args
        if not argv or argv[0] == "--background":
            argv.insert(0, "gui")  # double-clicked, or started by the login item

    parser = argparse.ArgumentParser(prog="airdrop-compress", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="watch in the foreground (default)")
    sub.add_parser("scan", help="convert files already in the AirDrop folder, then exit")
    gui = sub.add_parser("gui", help="start the menu bar app")
    gui.add_argument("--background", action="store_true", help="start without opening the window")
    plugin = sub.add_parser("plugin", help="plugin developer tools")
    plugin.add_argument("action", choices=["validate"])
    plugin.add_argument("folder", type=Path)
    sub.add_parser("settings", help="show the settings file")
    # v1 compatibility
    parser.add_argument("--scan-existing", action="store_true", help=argparse.SUPPRESS)
    args, _unknown = parser.parse_known_args(argv)

    command = args.command or ("scan" if args.scan_existing else "run")
    if command == "gui":
        setup_logging(to_file=True)
        from .ui.app import run_app
        return run_app(background=args.background)
    if command == "plugin":
        return validate_plugin(args.folder)
    if command == "settings":
        from .settings import SettingsManager
        print(paths.SETTINGS_FILE)
        print(json.dumps(SettingsManager().current.to_dict(), indent=2))
        return 0
    setup_logging(to_file=False)
    return run_watcher(scan_once=command == "scan")


if __name__ == "__main__":
    sys.exit(main())
