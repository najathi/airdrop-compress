# Architecture

```
airdrop_compress/
├── __main__.py        entry point: gui | run | scan | plugin validate | settings | --plugin-host
├── engine.py          watcher: detects new files, filters, de-duplicates, routes to processors, places outputs
├── settings.py        typed settings sections, validation, settings.json persistence, change listeners
├── store.py           duplicate protection (SHA-256 of each processed file -> its outputs)
├── activity.py        recent activity + daily statistics for the dashboard
├── macos.py           notifications, Finder, quarantine tags, launch-at-login LaunchAgent
├── paths.py           where data lives; resources inside the .app
├── processors/
│   ├── base.py        Processor protocol, Job, Output, Result, SkipFile
│   ├── images.py      WebP / AVIF / JPEG / Auto encoder, target size, srcset, metadata, colour
│   └── documents.py   Markdown via MarkItDown, macOS textutil, or fenced code
├── plugins/
│   ├── api.py         the only public plugin API (PluginContext, API_VERSION, PERMISSIONS)
│   ├── manager.py     discovery, manifest validation, approval, sandbox profile, running, output checks
│   └── host.py        runs inside the sandboxed child process and calls the plugin's process(ctx)
└── ui/
    ├── app.py         menu bar app lifecycle (window, login item, v1 migration)
    ├── menubar.py     NSStatusItem menu
    ├── api.py         JavaScript bridge (window.pywebview.api)
    └── web/           index.html, styles.css, app.js, icon.svg
```

## Flow of a file

1. **Detect.** FSEvents (watchdog) reports a created, moved or modified file in the watched folder, and a 30-second rescan catches any missed events. A file is new if its name and inode weren't there when watching started.
2. **Route.** `Engine.route` asks enabled plugins first, then the built-in image and document processors. Files nothing can handle are logged once as skipped.
3. **Wait and filter.** The engine waits until the file stops growing, then skips web downloads by checking the quarantine tag's agent name. It hashes the file and asks the store whether it was already converted.
4. **Process.** The processor gets a `Job` with the source file, a private `workdir` inside the output folder, and a snapshot of the settings. It writes its results to the workdir and returns `Output`s (each a path plus a suffix such as `.webp` or `-800w.webp`).
5. **Place.** The engine picks one free stem for all of a file's outputs, so `IMG_1.HEIC` and `IMG_1.JPG` become `IMG_1.*` and `IMG_1-1.*`. It then moves the outputs into place with `os.replace` (same disk, so the move is atomic) and records them in the store and the activity log.

## Concurrency and safety

- A lock file (`engine.lock`, `flock`) allows only one engine to run, whether it's the app or the command line.
- Settings, the store and the activity log are written atomically (temporary file plus `os.replace`). The store and settings also take a file lock, because the app and a `scan` run may write at the same time.
- Settings listeners run outside the settings lock, so pausing from the UI can't deadlock with the watcher thread.
- Originals are only ever opened for reading.

## Adding a built-in processor

Implement the `Processor` protocol in `processors/` (`id`, `name`, `kind`, `handles(path, settings)`, `process(job) -> Result`). Add it to `Engine.builtins`, and add a settings section to `settings.py` if it needs one. The UI reads settings through `describe()` and binds controls with `data-setting="section.key"`.

## Packaging

`packaging/build.sh` runs the tests, renders the icon (`qlmanage` → `sips` → `iconutil`), builds the `.app` with PyInstaller (`packaging/AirDropCompress.spec`), and signs it. Signing is ad-hoc, or uses Developer ID with the hardened runtime when `SIGN_IDENTITY` is set. The script then builds a `.dmg` and notarises it when `NOTARY_PROFILE` is set. `LSUIElement` keeps the app out of the Dock.
