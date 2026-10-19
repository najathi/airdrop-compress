# Changelog

## 2.1.0 - 2026-10-19

### Security
- **Stronger plugin sandbox.** The sandbox is now an allowlist. Plugins can no longer read the clipboard, talk to other apps or system services (Launch Services, Apple Events), or list or read shared and temporary folders.
- **Documents are converted in a sandboxed process** with a 5-minute limit, isolating PDF, Office, EPUB and ZIP parsers from the app.
- **Zip-bomb protection:** archives and Office files that would expand to an unsafe size are skipped (a 600 KB file previously kept a conversion busy for a minute and used about 1 GB of memory).
- **Plugin manifests are strictly validated** and everything shown in the app is escaped (a crafted manifest could inject content into the app window). The app window now has a Content-Security-Policy.
- Plugin installs from folders reject symbolic links. Plugins can't create executable or launcher file types. Outputs keep the source file's quarantine tag.
- Symbolic links in the AirDrop folder are never followed.
- The update check accepts only plain version numbers and links to this repository.
- Settings, history and logs are now readable only by your user account.

### Added
- "Built by" and **Build an app that meets your needs** sections in About, with business inquiry and contact links, plus a small *Need a custom solution?* link in the sidebar.
- Website with documentation: https://najathi.github.io/airdrop-compress/
- Documentation: Install, User Guide, Formats, Troubleshooting, FAQ, Releasing, Deployment, Security audit; `CONTRIBUTING.md`, `SECURITY.md`, issue templates, CI.

### Fixed
- Empty files no longer block a conversion slot for five minutes.
- Choosing the AirDrop folder itself as the output folder no longer causes an endless conversion loop; the app shows an error instead.
- Very long file names are shortened instead of failing.
- Clearer error messages, for example "Not a valid image, or the file is damaged".
- Notifications show "→" correctly instead of `\u2192`.
- Long-running sessions no longer accumulate memory for deleted files.

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
