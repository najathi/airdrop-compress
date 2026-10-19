# Security policy

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

Report them privately through [GitHub's private vulnerability reporting](https://github.com/najathi/airdrop-compress/security/advisories/new), or by email to **najathi777@gmail.com** with the subject `SECURITY: AirDrop Compress`.

Please include the affected version, steps to reproduce, and the impact you expect. I aim to acknowledge reports within a few working days and to fix confirmed issues as quickly as possible. You'll be credited in the release notes unless you prefer not to be.

## Supported versions

| Version | Supported |
|---|---|
| 2.1.x | ✅ (2.1.1 or later recommended) |
| 2.0.x | Upgrade to 2.1 (it contains security fixes) |
| 1.x | ❌ |

## Security model

AirDrop Compress automatically processes files that other people send you. AirDrop can be set to receive from *Everyone for 10 minutes*, so incoming files are treated as **untrusted**.

| Risk | Protection |
|---|---|
| Malicious documents exploiting a parser (PDF, Office, EPUB, ZIP…) | Documents are converted in a **separate sandboxed process** (`sandbox-exec`). It can read only the document and the Python runtime, write only to a private scratch folder, and has no network, no access to other apps or system services (clipboard, Apple Events), and no other programs. Conversions are stopped after 5 minutes. |
| Zip bombs / decompression bombs | ZIP-based files are checked before unpacking (300 MB unpacked, 5,000 files, compression ratio). Images above about 178 megapixels are refused. Document size limit (default 100 MB). |
| Symbolic links planted in the AirDrop folder | Links are never followed. |
| Files from browsers or other apps | Only files AirDrop delivered are converted by default (macOS quarantine agent check). |
| Overwriting or deleting files | Originals are opened read-only. Results get unique names and are moved into place atomically; nothing is overwritten. |
| Output re-processing loops | The output folder may not be the watched folder. |
| Gatekeeper bypass through generated files | Outputs keep the source's quarantine tag. Plugins can't create executable or launcher types (`.app`, `.command`, `.pkg`, `.webloc`, …). |
| Malicious or compromised plugins | Plugins are off until approved; approval is bound to a SHA-256 hash of the plugin's files. They run in the same sandbox as documents, with network or program access only if the user approves those permissions. Outputs are checked against the declared types; folder and zip installs reject links and path traversal. |
| Script injection in the app window | All data is escaped before display. Plugin manifests are strictly validated. The window has a Content-Security-Policy and loads only local files. |
| Command injection | External programs are run with fixed absolute paths and argument lists, never through a shell. |
| Update mechanism | The update check uses HTTPS with certificate verification, accepts only a plain version number, and only opens links to this repository on github.com. Nothing is downloaded or installed automatically. |
| Local data exposure | Settings, history and logs are in folders only your user can read (mode 700). |
| Secrets | The project has no API keys or credentials. The website is static and has none either. |

Known limitations and the full audit are in [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).

## Recommendations for users

- Set **AirDrop → Contacts Only** if you don't need to receive from strangers.
- Only install plugins from people you trust, and read the permissions before approving.
- Keep the app up to date. The update check tells you when there's a new version.
