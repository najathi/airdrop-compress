# Writing plugins for AirDrop Compress

A plugin adds support for a file type, or replaces how an existing type is converted. When a file you receive matches one of the plugin's file types, AirDrop Compress hands it to the plugin. The plugin writes its results, and the app saves them to the output folder next to the built-in conversions.

Plugins are written in Python. They run in a sandbox and can only do what the user approved.

## Quick start

A plugin is a folder with two files:

```
my-plugin/
├── plugin.json     the manifest: what the plugin is and what it needs
└── plugin.py       the code: a process(ctx) function
```

**plugin.json**

```json
{
  "id": "uppercase-text",
  "name": "Uppercase Text",
  "version": "1.0.0",
  "description": "Turns .txt files into SHOUTING .txt files.",
  "author": "Your Name",
  "homepage": "https://example.com",
  "api_version": 1,
  "min_app_version": "2.0.0",
  "entry": "plugin.py",
  "file_types": [".txt"],
  "outputs": [".txt"],
  "permissions": [],
  "timeout": 60,
  "settings": [
    {"key": "add_banner", "label": "Add a banner line", "type": "bool", "default": true}
  ]
}
```

**plugin.py**

```python
def process(ctx):
    text = ctx.input.read_text(encoding="utf-8")
    if not text.strip():
        ctx.skip("the file is empty")          # not an error - shown as "Skipped"
    if ctx.settings["add_banner"]:
        text = "CONVERTED BY UPPERCASE TEXT\n\n" + text
    ctx.output(".txt", label="Uppercase").write_text(text.upper(), encoding="utf-8")
    ctx.log(f"converted {len(text)} characters")
```

Check the plugin, then install it:

```bash
python -m airdrop_compress plugin validate my-plugin        # from a source checkout
"/Applications/AirDrop Compress.app/Contents/MacOS/AirDrop Compress" plugin validate my-plugin
```

In the app, go to **Plugins → Install from folder…** (or **Install plugin…** for a `.zip` of the folder). Then turn the plugin on and approve it.

A complete working example is in [`examples/plugins/svg-minify`](../examples/plugins/svg-minify).

## The manifest

| Field | Required | Description |
|---|---|---|
| `id` | yes | Unique ID: 2–41 lowercase letters, digits or dashes. It's also the install folder's name. |
| `name` | yes | Shown in the app. |
| `version` | yes | Your plugin's version, `MAJOR.MINOR.PATCH`. |
| `api_version` | yes | The plugin API you target. The current API is **1**. |
| `min_app_version` | yes | The oldest AirDrop Compress version your plugin works with, e.g. `"2.0.0"`. |
| `entry` | yes | The Python file that defines `process(ctx)`, relative to the plugin folder. |
| `file_types` | yes | Extensions the plugin handles, lowercase with a dot: `[".svg"]`. |
| `outputs` | yes | Extensions the plugin may create. Any other type is rejected. Types that can run code or open other apps when double-clicked (`.app`, `.command`, `.sh`, `.pkg`, `.dmg`, `.scpt`, `.workflow`, `.jar`, `.webloc`, `.fileloc`, …) aren't allowed. |
| `permissions` | no | Extra capabilities, see [Permissions](#permissions). Default: none. |
| `timeout` | no | Seconds per file before the plugin is stopped (1–600, default 120). |
| `settings` | no | Settings shown in the app, see [Settings](#settings). |
| `description`, `author`, `homepage` | no | Shown on the plugin's card. |

## The `ctx` object

`process(ctx)` receives a `PluginContext` (see `airdrop_compress/plugins/api.py`):

| Member | Description |
|---|---|
| `ctx.input` | `Path` of the received file. Read it, never modify it. |
| `ctx.output(suffix, label="")` | Reserves an output and returns the `Path` to write it to. The suffix is added to the original name, so `".svg"` gives `logo.svg` and `"-small.png"` gives `logo-small.png`. The app chooses a unique final name. Up to 20 outputs per file. |
| `ctx.settings` | `dict` of this plugin's settings, already validated. |
| `ctx.skip(reason)` | Stops processing this file without an error. The reason appears in the activity list. |
| `ctx.log(message)` | Writes a line to the app's log. `print()` also goes to the log. |
| `ctx.output_dir` | The private folder outputs are written to. You rarely need it. |

If `process` raises an exception, the file is marked **Failed** with the error message, and the traceback goes to the log.

## Which plugin handles a file?

Enabled plugins are asked first, in alphabetical order of their folder names. Built-in converters come after. A plugin that lists `.pdf` therefore replaces the built-in PDF-to-Markdown converter while it's on. This lets you write, for example, an OCR plugin for scanned PDFs. Turn the plugin off and the built-in converter is used again.

## Settings

Each entry in `settings` becomes a control on the plugin's card:

| `type` | Control | Extra keys |
|---|---|---|
| `bool` | switch | `default` |
| `int` | number field | `default`, `min`, `max` |
| `string` | text field | `default` (values are capped at 2000 characters) |
| `choice` | drop-down | `default`, `options` (a list of strings) |

Every entry also takes `key` (required: letters, digits and underscores), `label`, and `help` (a hint shown below the label; at most 200 characters each). `min` and `max` must be whole numbers, `options` must be text, and `default` must match the type, otherwise the manifest is rejected. Values are validated before your plugin sees them. A missing or invalid value falls back to `default`.

## Permissions

By default a plugin can:

- read the file it's converting, and files inside its own folder;
- write files to its private output folder (through `ctx.output`);
- use the Python standard library and the libraries bundled with the app (Pillow, pillow-heif and others).

Everything else is blocked by the macOS sandbox. The sandbox is an allowlist: only the system libraries, the Python runtime, the input file, the plugin's folder and its scratch folder are readable. That means a plugin can't:

- read your other files, list folders, or read the app's settings and history;
- talk to other apps or system services: no clipboard, no Apple Events, no opening URLs or apps through Launch Services;
- use the network or run other programs (unless approved, below).

Inside the plugin, `HOME` and the temporary folder both point to its scratch folder. Ask for more only if you need it:

| Permission | Allows | The user sees |
|---|---|---|
| `network` | Internet access, for example to call a web API | "Connect to the internet" |
| `subprocess` | Running other programs, for example `tesseract` for OCR | "Run other programs on this Mac" |

Users approve these permissions when they turn the plugin on. File access can't be widened.

## Security model

- **Off by default.** An installed plugin does nothing until the user turns it on and approves its permissions.
- **Approval is tied to the code.** The app stores a SHA-256 hash of every file in the plugin folder when the user approves it. If any file changes, through an update or tampering, the plugin shows **Changed – approve again** and doesn't run. The hash is checked again right before each run.
- **Sandboxed process.** Each file is processed in a separate process started with `sandbox-exec` and a profile generated for that run. If the sandbox isn't available, plugins don't run at all.
- **Checked outputs.** Output names must be simple and must use a declared type. Symlinks are rejected, at most 20 outputs are allowed, and the app moves the files into place itself. A plugin can't overwrite or delete anything.
- **Limits.** Per-file timeout, plugin folders up to 50 MB, and installs (folder or zip) are refused if they contain links or path traversal.
- **Strict manifests.** Everything the app displays from a manifest is type-checked and escaped, so a manifest can't inject content into the app's window.
- **Quarantine kept.** Outputs inherit the source file's macOS quarantine tag.
- **Isolation from the app.** The plugin process gets a minimal environment, with `HOME` and `TMPDIR` pointing to a scratch folder. It never sees the app's settings, history or other plugins' settings.

## Compatibility and versioning

- Bump `version` when you release. Users have to re-approve after an update, because the hash changes.
- The app refuses plugins whose `api_version` it doesn't support, or whose `min_app_version` is newer than the app. The plugin card explains why.
- API 1 is stable for all 2.x releases. A breaking change would introduce `api_version: 2`, and the app would keep supporting version 1 for at least one major release.
- Only import from `airdrop_compress.plugins.api`. Everything else in `airdrop_compress` is internal and may change.

## Dependencies

Plugins run on the Python bundled in the app, so only the standard library and the app's bundled libraries are available. To use something else:

- vendor pure-Python packages into your plugin folder (it's on `sys.path`), or
- call an external program with the `subprocess` permission, and tell users to install it.

## Distributing

Zip the plugin folder (the zip may contain the folder itself or just its contents) and share the `.zip`. Users install it with **Plugins → Install plugin…**. Installing a plugin with the same `id` asks before replacing it.

## Testing tips

- `plugin validate <folder>` checks the manifest without installing anything.
- Run the app from source with a temporary profile, so your real settings stay untouched:

  ```bash
  AIRDROP_COMPRESS_HOME=/tmp/adc-dev AIRDROP_DIR=/tmp/adc-inbox python -m airdrop_compress gui
  ```

  Copy your plugin into `/tmp/adc-dev/plugins/`, turn it on, then drop files onto the dashboard.
- `tests/test_plugins.py` shows how to test plugins with pytest, including the sandbox.
