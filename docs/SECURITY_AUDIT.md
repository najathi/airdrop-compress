# Security audit: version 2.1.0

**Date:** 19 October 2026 · **Scope:** the app (engine, processors, plugins, UI bridge), build and packaging scripts, the update mechanism, the GitHub repository, and the website.

## Method

- Manual review of every module, focused on how untrusted files from AirDrop flow through the app.
- Proof-of-concept tests for each suspected issue (malicious plugins, zip bombs, symlinks, crafted manifests). Each confirmed issue now has a regression test in `tests/`.
- `bandit` static analysis. Its only findings were expected `subprocess` usage (fixed binaries, argument lists, no shell) and one `urlopen` to a fixed HTTPS URL.
- `pip-audit` on all dependencies: **no known vulnerabilities**.
- A secret scan of the full git history (API keys, tokens, private keys, passwords): **none found**.

## Findings and fixes

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | High | **Plugin sandbox allowed access to system services and shared folders.** A plugin with no permissions could read the clipboard, query Launch Services (a way to open URLs, so data could leave without network permission), and list `/Users/Shared`, `/private/tmp` and other apps' temporary folders. | **Fixed:** allowlist profile (`airdrop_compress/sandbox.py`). All file reads are denied except system libraries, the runtime, the input file and the plugin's own folders. System-service (mach) lookups are denied except logging; Apple Events are denied. Tests: `test_sandbox_blocks_*`. |
| 2 | High | **Untrusted documents were parsed inside the app process.** PDF, Office, EPUB and ZIP parsers ran with the app's full permissions and no time limit. | **Fixed:** documents are converted by `document_worker` in a sandboxed child process (read only the document, no network, no services) with a 5-minute timeout. Tests: `test_office_formats_in_sandbox`, `test_damaged_pdf_has_a_clear_error`. |
| 3 | Medium | **Zip bomb denial of service.** A 597 KB `.zip` kept a conversion busy for 63 seconds and used about 926 MB of memory. | **Fixed:** ZIP-based files are checked before unpacking (300 MB unpacked, 5,000 entries, ratio above 200). Test: `test_zip_bomb_is_skipped`. |
| 4 | Medium | **Script injection into the app window through a plugin manifest.** A plugin setting's `min`/`max` value was inserted into the settings form without escaping. Script running there could call the app's bridge (enable plugins, uninstall…). | **Fixed:** manifest settings are strictly type-checked, every value shown is escaped, and the window has a Content-Security-Policy. Tests: `test_manifest_hardening`. |
| 5 | Medium | **Plugin folder installs followed symbolic links,** copying files from elsewhere on the Mac (for example `~/.ssh`) into the plugin folder, where the plugin could read them. | **Fixed:** folder installs with links are refused (zip installs already were). Test: `test_folder_install_rejects_links`. |
| 6 | Medium | **Gatekeeper bypass through generated files.** Outputs didn't keep the source's quarantine tag, and a plugin could declare executable or launcher outputs (`.command`, `.app`, `.webloc`…). | **Fixed:** outputs inherit the source's quarantine tag, and those types are forbidden in manifests. Tests: `test_long_names_and_quarantine_are_kept`, `test_manifest_hardening`. |
| 7 | Low | **Symbolic links in the AirDrop folder were followed,** so a link to a private file could be converted into the output folder. | **Fixed:** links are skipped. Test: `test_symlinks_are_never_followed`. |
| 8 | Low | **The update check trusted the release data:** any tag text and download URL were used. | **Fixed:** only `X.Y.Z` versions and links to this repository on github.com are accepted. Test: `test_update_check_rejects_unexpected_data`. |
| 9 | Low | **App data was readable by other local users** (folders created with mode 755). The history contains received file names. | **Fixed:** the data and log folders are mode 700. |
| 10 | Low | **Unsafe output folder:** setting the output folder to the AirDrop folder caused an endless conversion loop (unbounded disk use). | **Fixed:** refused, with an explanation. Test: `test_output_folder_cannot_be_the_watch_folder`. |

### Reliability issues fixed during the audit

- Empty files kept a conversion slot busy for 5 minutes. They're now skipped after about 3 seconds.
- File names near the 255-byte limit made conversions fail. They're now shortened.
- Error messages showed raw library text and full paths. They now show plain language ("Not a valid image, or the file is damaged").
- Notification text showed `→` instead of "→" (AppleScript doesn't understand JSON escapes).
- Memory grew slowly in long sessions (the record of seen files was never pruned).

## Reviewed and found sound

- **Command execution:** every external program (`xattr`, `textutil`, `osascript`, `launchctl`, `open`, `sandbox-exec`) is called with an absolute path and an argument list, never through a shell. AppleScript strings are JSON-escaped, and inputs are counts, versions or our own paths.
- **Path handling:** outputs are always named by the app (sanitised stem plus a validated suffix) inside the output folder. "Reveal in Finder" only accepts names inside the output folder. Folder shortcuts in the UI are an allowlist.
- **Temporary files:** per-file work folders are created with `mkdtemp` (mode 700) inside the output folder and removed afterwards. Settings and history are written atomically under a file lock.
- **Originals:** only ever opened for reading.
- **Website:** static files only. No secrets, cookies, third-party scripts, fonts or trackers. Strict CSP.
- **Repository:** no credentials. CI uses read-only permissions; the Pages workflow only gets `pages: write` and `id-token: write`.

## Known limitations

| Item | Notes |
|---|---|
| **Not notarised** | The release is ad-hoc signed, so users have to approve it once in Privacy & Security. This needs an Apple Developer ID; the build script supports signing and notarisation already. See [Releasing](RELEASING.md). |
| **Images are decoded in-process** | Pillow, libheif and libavif decode images inside the app, for speed. Mitigations: decompression-bomb limits, dependency updates via Dependabot, `pip-audit` in CI. Moving image decoding into the sandbox is possible if needed. |
| **`textutil` runs outside the sandbox** | Apple's own converter for `.doc`/`.rtf`/`.odt` needs system services the sandbox blocks. It runs with a 2-minute timeout, and its HTML output is then converted inside the sandbox. |
| **`sandbox-exec` is deprecated by Apple** | It still works on current macOS. If Apple removes it, plugins are disabled automatically, and documents fall back to in-process conversion with a warning in the log. |
| **`'unsafe-eval'` in the app's CSP** | Required by pywebview's JavaScript bridge. All displayed data is escaped, and no remote content is loaded. |
| **GitHub Pages can't send security headers** | CSP and referrer policy are set with `<meta>` tags. `X-Frame-Options`/HSTS need another host; `site/_headers` is ready for Cloudflare Pages or Netlify. |
| **Dependencies aren't hash-pinned** | `requirements.txt` uses minimum versions. Dependabot and `pip-audit` watch for vulnerable versions; reproducible release builds should pin exact versions. |
| **Commit author email is public** | Commits use the author's personal email. To hide it in future commits, use GitHub's `noreply` address (GitHub → Settings → Emails). |
