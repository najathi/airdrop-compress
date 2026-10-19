"""Discovers, validates, authorises and runs plugins.

Security model
--------------
* Plugins are off until the user enables them and approves the permissions their
  manifest asks for. The approval is tied to a hash of the plugin's files: if any
  file changes (update, tampering), the plugin is disabled until approved again.
* Each call runs in a separate process under the macOS sandbox (sandbox-exec):
  it can read only the incoming file, its own folder and the Python runtime; it
  can write only to a private scratch folder; network access and starting other
  programs are blocked unless the matching permission was approved. The plugin
  never sees the app's settings, history or other files.
* Outputs are checked (count, names, declared types, no symlinks) before the
  engine moves them into the output folder. Calls are killed after a timeout.
* If the sandbox isn't available, plugins don't run at all (fail closed).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import __version__, paths
from ..processors.base import Job, Output, Result, SkipFile
from ..settings import Settings, SettingsManager
from .api import MAX_OUTPUTS, PERMISSIONS, SUFFIX_RE, SUPPORTED_API_VERSIONS
from .host import RESULT_MARK

log = logging.getLogger(__name__)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
EXT_RE = re.compile(r"^\.[a-z0-9]{1,10}$")
SETTING_TYPES = {"bool", "int", "string", "choice"}
MAX_PLUGIN_BYTES = 50 * 1024 * 1024
MAX_TIMEOUT = 600
SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


@dataclass
class PluginInfo:
    id: str
    path: str
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    api_version: int = 0
    min_app_version: str = "0.0.0"
    entry: str = "plugin.py"
    file_types: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    timeout: int = 120
    settings: list[dict] = field(default_factory=list)
    digest: str = ""
    errors: list[str] = field(default_factory=list)       # invalid manifest
    incompatible: str = ""                                 # valid, but not for this app version


def plugin_digest(folder: Path) -> str:
    h = hashlib.sha256()
    total = 0
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.name == ".DS_Store":
            continue
        total += f.stat().st_size
        if total > MAX_PLUGIN_BYTES:
            raise ValueError("plugin folder is larger than 50 MB")
        h.update(str(f.relative_to(folder)).encode() + b"\0")
        h.update(f.read_bytes())
    return h.hexdigest()


def load_manifest(folder: Path) -> PluginInfo:
    """Read and validate plugin.json. Never raises - problems end up in .errors."""
    info = PluginInfo(id=folder.name, path=str(folder))
    try:
        raw = json.loads((folder / "plugin.json").read_text())
        if not isinstance(raw, dict):
            raise ValueError("plugin.json must contain an object")
    except FileNotFoundError:
        info.errors.append("plugin.json is missing")
        return info
    except (ValueError, OSError) as e:
        info.errors.append(f"plugin.json can't be read: {e}")
        return info

    def get(key, typ, default):
        v = raw.get(key, default)
        if not isinstance(v, typ) or isinstance(v, bool) and typ is int:
            info.errors.append(f"'{key}' must be a {typ.__name__}")
            return default
        return v

    info.id = get("id", str, "")
    info.name = get("name", str, "") or info.id
    info.version = get("version", str, "0.0.0")
    info.description = get("description", str, "")
    info.author = get("author", str, "")
    info.homepage = get("homepage", str, "")
    info.api_version = get("api_version", int, 0)
    info.min_app_version = get("min_app_version", str, "0.0.0")
    info.entry = get("entry", str, "plugin.py")
    info.file_types = [t.lower() for t in get("file_types", list, []) if isinstance(t, str)]
    info.outputs = [t.lower() for t in get("outputs", list, []) if isinstance(t, str)]
    info.permissions = [p for p in get("permissions", list, []) if isinstance(p, str)]
    info.timeout = get("timeout", int, 120)
    info.settings = [s for s in get("settings", list, []) if isinstance(s, dict)]

    if not ID_RE.match(info.id):
        info.errors.append("'id' must be 2-41 lowercase letters, digits or dashes")
    if not VERSION_RE.match(info.version):
        info.errors.append("'version' must look like 1.0.0")
    if not VERSION_RE.match(info.min_app_version):
        info.errors.append("'min_app_version' must look like 2.0.0")
    if not info.file_types or not all(EXT_RE.match(t) for t in info.file_types):
        info.errors.append("'file_types' must list extensions like \".svg\"")
    if not info.outputs or not all(EXT_RE.match(t) for t in info.outputs):
        info.errors.append("'outputs' must list the extensions the plugin creates, like \".png\"")
    unknown = set(info.permissions) - set(PERMISSIONS)
    if unknown:
        info.errors.append(f"unknown permissions: {', '.join(sorted(unknown))}")
    if not 1 <= info.timeout <= MAX_TIMEOUT:
        info.errors.append(f"'timeout' must be 1-{MAX_TIMEOUT} seconds")
    entry = (folder / info.entry).resolve()
    if folder.resolve() not in entry.parents or not entry.is_file() or entry.suffix != ".py":
        info.errors.append(f"entry file '{info.entry}' must be a .py file inside the plugin folder")
    for s in info.settings:
        if not isinstance(s.get("key"), str) or s.get("type") not in SETTING_TYPES:
            info.errors.append("each setting needs a 'key' and a 'type' (bool, int, string or choice)")
            break
        if s["type"] == "choice" and not isinstance(s.get("options"), list):
            info.errors.append(f"setting '{s['key']}' needs 'options'")

    if not info.errors:
        if info.api_version not in SUPPORTED_API_VERSIONS:
            info.incompatible = (f"needs plugin API v{info.api_version}; this app supports "
                                 f"v{', v'.join(map(str, sorted(SUPPORTED_API_VERSIONS)))}")
        elif parse_version(info.min_app_version) > parse_version(__version__):
            info.incompatible = f"needs AirDrop Compress {info.min_app_version} or newer"
    try:
        info.digest = plugin_digest(folder)
    except (OSError, ValueError) as e:
        info.errors.append(str(e))
    return info


def validate_setting(spec: dict, value):
    t = spec["type"]
    if t == "bool" and isinstance(value, bool):
        return value
    if t == "int" and isinstance(value, int) and not isinstance(value, bool):
        if "min" in spec and value < spec["min"] or "max" in spec and value > spec["max"]:
            raise ValueError(f"{spec.get('label', spec['key'])} is out of range")
        return value
    if t == "string" and isinstance(value, str):
        return value[:2000]
    if t == "choice" and value in spec.get("options", []):
        return value
    raise ValueError(f"Invalid value for {spec.get('label', spec['key'])}")


def sandbox_profile(info: PluginInfo, input_path: Path, work: Path, runtime: list[Path]) -> str:
    def q(p: Path | str) -> str:
        return json.dumps(str(p))  # SBPL strings use the same escaping as JSON

    home = Path.home().resolve()
    reads = [f"(literal {q(input_path.resolve())})", f"(subpath {q(Path(info.path).resolve())})",
             f"(subpath {q(work.resolve())})"]
    reads += [f"(subpath {q(r.resolve())})" for r in runtime]
    # Python checks its parent folders on start-up; listing them reveals nothing else.
    for r in [*runtime, input_path, Path(info.path), work]:
        for parent in r.resolve().parents:
            reads.append(f"(literal {q(parent)})")
    rules = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        f"(allow file-write* (subpath {q(work.resolve())}) (literal \"/dev/null\") (literal \"/dev/stderr\")"
        " (literal \"/dev/stdout\") (literal \"/dev/tty\"))",
        f"(deny file-read* (subpath {q(home)}) (subpath \"/Volumes\"))",
        f"(allow file-read* {' '.join(dict.fromkeys(reads))})",
    ]
    if "network" not in info.permissions:
        rules.append("(deny network*)")
    if "subprocess" not in info.permissions:
        # Only the Python runtime itself may be started (its launcher re-executes the real binary).
        execs = " ".join(f"(subpath {q(r.resolve())})" for r in runtime)
        rules += ["(deny process-exec*)",
                  f"(allow process-exec* (literal {q(Path(sys.executable).resolve())}) {execs})"]
    return "\n".join(rules) + "\n"


def host_command() -> tuple[list[str], dict, list[Path]]:
    """Command that starts the plugin host, extra env, and runtime folders it must read."""
    if paths.is_frozen():
        bundle = paths.app_bundle() or Path(sys.executable).parent
        return [sys.executable, "--plugin-host"], {}, [bundle]
    runtime = {Path(sys.prefix), Path(sys.base_prefix), paths.PACKAGE_DIR}
    return ([sys.executable, "-s", "-B", "-m", "airdrop_compress.plugins.host"],
            {"PYTHONPATH": str(paths.PACKAGE_DIR.parent)}, sorted(runtime))


def sandbox_available() -> bool:
    return Path(SANDBOX_EXEC).exists()


class PluginProcessor:
    kind = "plugin"

    def __init__(self, info: PluginInfo, manager: "PluginManager"):
        self.info = info
        self.manager = manager
        self.id = f"plugin.{info.id}"
        self.name = info.name

    def handles(self, path: Path, settings: Settings) -> bool:
        return path.suffix.lower() in self.info.file_types

    def process(self, job: Job) -> Result:
        return self.manager.run(self.info, job)


class PluginManager:
    def __init__(self, settings: SettingsManager, plugins_dir: Path = paths.PLUGINS_DIR):
        self.settings = settings
        self.dir = plugins_dir
        self.plugins: dict[str, PluginInfo] = {}
        self.discover()

    # -- discovery ---------------------------------------------------------- #

    def discover(self) -> list[PluginInfo]:
        found: dict[str, PluginInfo] = {}
        if self.dir.is_dir():
            for folder in sorted(self.dir.iterdir()):
                if folder.is_dir() and not folder.name.startswith("."):
                    info = load_manifest(folder)
                    if info.id in found:
                        info.errors.append(f"another plugin already uses the id '{info.id}'")
                        info.id = f"{info.id}@{folder.name}"
                    found[info.id] = info
        self.plugins = found
        return list(found.values())

    def _state(self, plugin_id: str) -> dict:
        return dict(self.settings.current.plugins.get(plugin_id, {}))

    def _save_state(self, plugin_id: str, state: dict | None) -> None:
        plugins = dict(self.settings.current.plugins)
        if state is None:
            plugins.pop(plugin_id, None)
        else:
            plugins[plugin_id] = state
        self.settings.replace_plugins(plugins)

    def status(self, info: PluginInfo) -> str:
        """ok | disabled | needs_approval | changed | incompatible | invalid | no_sandbox"""
        if info.errors:
            return "invalid"
        if info.incompatible:
            return "incompatible"
        state = self._state(info.id)
        if not state.get("enabled"):
            return "disabled"
        approved = state.get("approved") or {}
        if approved.get("digest") != info.digest:
            return "changed" if approved else "needs_approval"
        if not set(info.permissions) <= set(approved.get("permissions", [])):
            return "needs_approval"
        if not sandbox_available():
            return "no_sandbox"
        return "ok"

    def processors(self) -> list[PluginProcessor]:
        return [PluginProcessor(i, self) for i in self.plugins.values() if self.status(i) == "ok"]

    # -- management --------------------------------------------------------- #

    def enable(self, plugin_id: str) -> None:
        """Enable and approve the plugin's current files and permissions."""
        info = self._get(plugin_id)
        if info.errors or info.incompatible:
            raise ValueError(info.errors[0] if info.errors else info.incompatible)
        state = self._state(plugin_id)
        state.update(enabled=True, approved={
            "digest": info.digest, "permissions": list(info.permissions),
            "version": info.version, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save_state(plugin_id, state)

    def disable(self, plugin_id: str) -> None:
        state = self._state(plugin_id)
        state["enabled"] = False
        self._save_state(plugin_id, state)

    def plugin_settings(self, info: PluginInfo) -> dict:
        saved = self._state(info.id).get("settings", {})
        values = {}
        for spec in info.settings:
            try:
                values[spec["key"]] = validate_setting(spec, saved[spec["key"]])
            except (KeyError, ValueError):
                values[spec["key"]] = spec.get("default")
        return values

    def update_settings(self, plugin_id: str, values: dict) -> dict:
        info = self._get(plugin_id)
        specs = {s["key"]: s for s in info.settings}
        clean = self.plugin_settings(info)
        for key, value in values.items():
            if key not in specs:
                raise ValueError(f"Unknown setting '{key}'")
            clean[key] = validate_setting(specs[key], value)
        state = self._state(plugin_id)
        state["settings"] = clean
        self._save_state(plugin_id, state)
        return clean

    def install(self, source: Path, replace: bool = False) -> PluginInfo:
        """Install from a plugin folder or a .zip of one."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.dir, prefix=".install-") as tmp:
            staging = Path(tmp) / "plugin"
            if source.is_file() and source.suffix.lower() == ".zip":
                self._extract_zip(source, staging)
            elif source.is_dir():
                shutil.copytree(source, staging, symlinks=False,
                                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", ".git"))
            else:
                raise ValueError("Choose a plugin folder or a .zip file")
            # A zip may wrap the plugin in one top-level folder.
            if not (staging / "plugin.json").exists():
                inner = [p for p in staging.iterdir() if p.is_dir()]
                if len(inner) == 1 and (inner[0] / "plugin.json").exists():
                    staging = inner[0]
            info = load_manifest(staging)
            if info.errors:
                raise ValueError("Not a valid plugin: " + "; ".join(info.errors))
            target = self.dir / info.id
            if target.exists():
                if not replace:
                    raise FileExistsError(f"A plugin with the id '{info.id}' is already installed")
                shutil.rmtree(target)
            shutil.move(str(staging), target)
        self.discover()
        return self.plugins[info.id]

    @staticmethod
    def _extract_zip(source: Path, dest: Path) -> None:
        dest.mkdir(parents=True)
        with zipfile.ZipFile(source) as z:
            total = 0
            for member in z.infolist():
                target = (dest / member.filename).resolve()
                if dest.resolve() not in target.parents and target != dest.resolve():
                    raise ValueError(f"Unsafe path in zip: {member.filename}")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Zip contains a symlink: {member.filename}")
                total += member.file_size
                if total > MAX_PLUGIN_BYTES:
                    raise ValueError("Plugin is larger than 50 MB")
            z.extractall(dest)

    def remove(self, plugin_id: str) -> None:
        info = self._get(plugin_id)
        folder = Path(info.path).resolve()
        if self.dir.resolve() not in folder.parents:
            raise ValueError("Plugin is outside the plugins folder")
        shutil.rmtree(folder)
        self._save_state(plugin_id, None)
        self.discover()

    def _get(self, plugin_id: str) -> PluginInfo:
        if plugin_id not in self.plugins:
            self.discover()
        if plugin_id not in self.plugins:
            raise KeyError(f"No plugin '{plugin_id}'")
        return self.plugins[plugin_id]

    def to_ui(self) -> list[dict]:
        out = []
        for info in self.plugins.values():
            d = asdict(info)
            d["status"] = self.status(info)
            d["enabled"] = bool(self._state(info.id).get("enabled"))
            d["values"] = self.plugin_settings(info) if not info.errors else {}
            d["permission_labels"] = {p: PERMISSIONS.get(p, p) for p in info.permissions}
            out.append(d)
        return out

    # -- running ------------------------------------------------------------ #

    def run(self, info: PluginInfo, job: Job) -> Result:
        if self.status(info) != "ok":
            raise RuntimeError(f"plugin {info.name} is not authorised to run")
        # Re-check the files right before running: approval covers exactly these bytes.
        if plugin_digest(Path(info.path)) != info.digest:
            raise RuntimeError(f"plugin {info.name} changed on disk - approve it again in Plugins")

        out_dir = job.workdir / "plugin-out"
        tmp_dir = job.workdir / "plugin-tmp"
        out_dir.mkdir()
        tmp_dir.mkdir()
        cmd, env_extra, runtime = host_command()
        profile = job.workdir / "sandbox.sb"
        profile.write_text(sandbox_profile(info, job.src, job.workdir, runtime))
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_dir), "TMPDIR": str(tmp_dir),
               "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", **env_extra}
        request = {"id": info.id, "plugin_dir": str(Path(info.path).resolve()), "entry": info.entry,
                   "input": str(job.src.resolve()), "output_dir": str(out_dir.resolve()),
                   "settings": self.plugin_settings(info)}
        try:
            proc = subprocess.run([SANDBOX_EXEC, "-f", str(profile), *cmd], input=json.dumps(request),
                                  capture_output=True, text=True, timeout=info.timeout, env=env,
                                  cwd=str(tmp_dir))
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"plugin {info.name} took longer than {info.timeout}s and was stopped")
        for line in proc.stderr.splitlines()[-50:]:
            log.info("[plugin %s] %s", info.id, line)
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith(RESULT_MARK):
                result = json.loads(line[len(RESULT_MARK):])
        if result is None:
            raise RuntimeError(f"plugin {info.name} crashed (exit code {proc.returncode})")
        if result.get("skip"):
            raise SkipFile(f"{info.name}: {result['skip']}")
        if not result.get("ok"):
            if result.get("trace"):
                log.error("[plugin %s] %s", info.id, result["trace"])
            raise RuntimeError(f"{info.name}: {result.get('error', 'failed')}")
        return Result(self._check_outputs(info, out_dir, result.get("outputs", [])), note=info.name)

    @staticmethod
    def _check_outputs(info: PluginInfo, out_dir: Path, outputs: list) -> list[Output]:
        if not isinstance(outputs, list) or len(outputs) > MAX_OUTPUTS:
            raise RuntimeError(f"{info.name} returned an invalid output list")
        checked = []
        for o in outputs:
            suffix, name = str(o.get("suffix", "")), str(o.get("file", ""))
            path = out_dir / name
            if "/" in name or not SUFFIX_RE.match(suffix):
                raise RuntimeError(f"{info.name} returned an invalid output name")
            ext = Path("x" + suffix).suffix.lower()
            if ext not in info.outputs:
                raise RuntimeError(f"{info.name} created a {ext} file, "
                                   f"but its manifest only declares {', '.join(info.outputs)}")
            if not path.exists():
                continue  # reserved but never written
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"{info.name} returned something that isn't a regular file")
            checked.append(Output(path, suffix, str(o.get("label", ""))[:40]))
        if not checked:
            raise SkipFile(f"{info.name} produced no output")
        return checked
