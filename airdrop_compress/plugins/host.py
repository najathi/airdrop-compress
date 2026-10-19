"""Runs one plugin call inside the sandboxed child process.

Started by PluginManager as ``<app> --plugin-host`` (packaged app) or
``python -m airdrop_compress.plugins.host``. Reads one JSON request on stdin and
prints one JSON result line, prefixed with RESULT_MARK, on stdout.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path

RESULT_MARK = "@@AIRDROP-COMPRESS-RESULT@@"


def run(request: dict) -> dict:
    from .api import PluginContext, PluginSkip

    plugin_dir = Path(request["plugin_dir"])
    ctx = PluginContext(Path(request["input"]), Path(request["output_dir"]),
                        request.get("settings", {}), request["id"])
    sys.path.insert(0, str(plugin_dir))  # let the plugin import its own helper modules
    try:
        spec = importlib.util.spec_from_file_location(
            f"airdrop_compress_plugin_{request['id'].replace('-', '_')}", plugin_dir / request["entry"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, "process", None)):
            return {"ok": False, "error": "the plugin has no process(ctx) function"}
        module.process(ctx)
    except PluginSkip as e:
        return {"ok": False, "skip": str(e) or "skipped by plugin"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(limit=8)}
    return {"ok": True, "outputs": ctx.outputs}


def main() -> int:
    request = json.loads(sys.stdin.read())
    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # anything the plugin prints goes to the log, not the result channel
    try:
        result = run(request)
    finally:
        sys.stdout = real_stdout
    print(RESULT_MARK + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
