# Changelog

## 2.0.0 - 2026-10-19

### Added
- **Menu bar app** with a dashboard and settings window: live status, today's savings, an activity list with progress and errors, drag and drop to convert, and pause/resume. It opens at login (optional) and has no Dock icon.
- **Image formats:** WebP (default), AVIF, JPEG, and **Auto**, which encodes each format and keeps the smallest.
- **Image options:** quality per format, compression effort, target file size, maximum dimension, responsive `srcset` sizes, metadata (keep / remove location / remove all), sRGB conversion, SEO-friendly file names, JPEG fallback, lossless WebP for PNG graphics, progressive JPEG, and skip-if-larger.
- A **Compare formats** tool that shows one of your images' size in each format.
- **Plugins:** manifest, versioned API, approval and permissions, sandboxed execution, install from a folder or `.zip`, auto-generated settings, and an example SVG minifier. See `docs/PLUGINS.md`.
- **Settings** saved in `~/Library/Application Support/AirDropCompress/settings.json` and shared by the app and the command line.
- **Installer:** `packaging/build.sh` builds `AirDrop Compress.app` and a `.dmg`, with Developer ID signing and notarisation available.
- In-app update check (GitHub releases) and uninstall.
- Test suite (pytest).
- Installer window with drag-to-Applications artwork and an illustrated "How to open" guide for the first launch.

### Changed
- The output folder is `airdrop-compress` (it was `Image Compressed`, which is renamed automatically).
- The code is now a package (`airdrop_compress/`); `airdrop_compress.py` was removed. The `./airdrop-compress` command line still works. After updating, run `./airdrop-compress restart` or switch to the app. The app offers to remove the v1 service.
- Only one watcher (app or command line) can run at a time.
- Files that arrive while processing is paused are no longer converted when you resume.

## 1.0.0
- Watches the AirDrop folder; converts images to WebP and documents to Markdown; LaunchAgent with install, enable, disable, status and logs commands.
