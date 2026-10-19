"""macOS sandbox (sandbox-exec) profiles for code that handles untrusted input.

Used for plugins and for document conversion: files received via AirDrop can come
from anyone nearby, so complex parsers run in a separate process that
- can read only the system/runtime files Python needs, plus the one input file;
- can write only to a private scratch folder;
- can't talk to other apps or system services (clipboard, Launch Services,
  Apple Events...), use the network, or start other programs - unless allowed.

The profile is an allowlist: everything not listed is denied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import paths

SANDBOX_EXEC = "/usr/bin/sandbox-exec"

# Read-only system locations the Python runtime and its libraries need.
SYSTEM_READ = [
    "/System", "/usr", "/bin", "/sbin", "/dev",
    "/private/etc", "/private/var/db/timezone", "/private/var/db/dyld",
    "/Library/Preferences/Logging",
]
# System services (mach) a sandboxed Python process may contact: logging only.
BASE_SERVICES = [
    "com.apple.system.logger", "com.apple.logd", "com.apple.diagnosticd",
    "com.apple.system.notification_center", "com.apple.system.opendirectoryd.libinfo",
]
# Extra services needed for DNS and TLS when network access is granted.
NETWORK_SERVICES = [
    "com.apple.dnssd.service", "com.apple.trustd", "com.apple.trustd.agent",
    "com.apple.SystemConfiguration.configd", "com.apple.SystemConfiguration.DNSConfiguration",
    "com.apple.networkd", "com.apple.nehelper",
]


def available() -> bool:
    return Path(SANDBOX_EXEC).exists()


def _q(p: Path | str) -> str:
    return json.dumps(str(p))  # SBPL strings use the same escaping as JSON


def runtime_paths() -> list[Path]:
    """Folders holding the Python runtime and this app's code."""
    if paths.is_frozen():
        return [paths.app_bundle() or Path(sys.executable).parent]
    return sorted({Path(sys.prefix), Path(sys.base_prefix), paths.PACKAGE_DIR})


def python_command(module: str, frozen_flag: str) -> tuple[list[str], dict]:
    """Command that runs `module` (source) or the app binary with `frozen_flag` (packaged)."""
    if paths.is_frozen():
        return [sys.executable, frozen_flag], {}
    return ([sys.executable, "-s", "-B", "-m", module], {"PYTHONPATH": str(paths.PACKAGE_DIR.parent)})


def profile(*, read_files: list[Path] = (), read_dirs: list[Path] = (), write_dir: Path,
            network: bool = False, run_programs: bool = False) -> str:
    runtime = [r.resolve() for r in runtime_paths()]
    write_dir = write_dir.resolve()
    # "/" itself: dyld lists the root folder while loading (top-level names only).
    reads = ['(literal "/")'] + [f"(subpath {_q(p)})" for p in SYSTEM_READ]
    reads += [f"(subpath {_q(r)})" for r in runtime]
    reads += [f"(subpath {_q(Path(d).resolve())})" for d in read_dirs]
    reads += [f"(literal {_q(Path(f).resolve())})" for f in read_files]
    reads.append(f"(subpath {_q(write_dir)})")
    if not paths.is_frozen():
        # Running from source: Python lists the project folder to find the package on PYTHONPATH.
        reads.append(f"(literal {_q(paths.PACKAGE_DIR.parent.resolve())})")

    services = BASE_SERVICES + (NETWORK_SERVICES if network else [])
    rules = [
        "(version 1)",
        "(allow default)",
        # Files: read only what's listed; metadata (exists/size) is allowed so paths resolve.
        "(deny file-read*)",
        "(allow file-read-metadata)",
        f"(allow file-read* {' '.join(dict.fromkeys(reads))})",
        "(deny file-write*)",
        f"(allow file-write* (subpath {_q(write_dir)}) (literal \"/dev/null\") (literal \"/dev/stdout\")"
        " (literal \"/dev/stderr\") (literal \"/dev/dtracehelper\"))",
        # No talking to other apps or system services (clipboard, Launch Services, Apple Events...).
        "(deny mach-lookup)",
        "(allow mach-lookup " + " ".join(f"(global-name {_q(s)})" for s in services) + ")",
        "(deny appleevent-send)",
    ]
    if not network:
        rules.append("(deny network*)")
    if not run_programs:
        # Only the Python runtime itself may start (python.org's launcher re-executes the real binary).
        execs = " ".join(f"(subpath {_q(r)})" for r in runtime)
        rules += ["(deny process-exec*)",
                  f"(allow process-exec* (literal {_q(Path(sys.executable).resolve())}) {execs})"]
    return "\n".join(rules) + "\n"


def command(profile_path: Path, cmd: list[str]) -> list[str]:
    return [SANDBOX_EXEC, "-f", str(profile_path), *cmd]
