# Building and releasing

## Build the app

```bash
packaging/build.sh
```

This:

1. installs the build dependencies (`requirements-dev.txt`) and runs the tests;
2. renders the app icon (`qlmanage` → `sips` → `iconutil`);
3. builds `dist/AirDrop Compress.app` with PyInstaller (`packaging/AirDropCompress.spec`);
4. signs it: ad-hoc by default, or with your Developer ID (see below);
5. smoke-tests the binary;
6. creates the disk image with `dmgbuild`, including the drag-to-Applications window and the *How to open* guide:
   - `dist/AirDrop-Compress-<version>-<arch>.dmg`
   - `dist/AirDrop-Compress-<arch>.dmg`, an identical copy with a stable name, used by the website's download button.

The app is built for the architecture of the Mac you build on (`arm64` or `x86_64`).

## Signing and notarisation

Without a Developer ID the app is ad-hoc signed, and users confirm the first launch once (see [Install](INSTALL.md#the-first-launch)). To sign and notarise:

1. Join the [Apple Developer Program](https://developer.apple.com/programs/). The **Account Holder** creates a *Developer ID Application* certificate (Xcode → Settings → Accounts → Manage Certificates).
2. Store notarisation credentials once:
   ```bash
   xcrun notarytool store-credentials airdrop-compress --apple-id YOU@EXAMPLE.COM --team-id TEAMID
   ```
3. Build:
   ```bash
   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" NOTARY_PROFILE=airdrop-compress packaging/build.sh
   ```

The build signs with the hardened runtime and `packaging/entitlements.plist`, then notarises and staples the `.dmg`. Credentials stay in your Keychain and are never written to the repository.

## Release checklist

1. Update `__version__` in `airdrop_compress/__init__.py` and add a section to `CHANGELOG.md`.
2. Run the checks:
   ```bash
   .venv/bin/python -m pytest
   .venv/bin/pip-audit -r requirements.txt
   ```
3. Build: `packaging/build.sh`.
4. Install the `.dmg` on a clean account or another Mac if you can. Check the first launch, the folder permission prompt, an AirDrop conversion, and *Open at login* after logging out and back in.
5. Merge to `main`, then publish the release with both disk images:
   ```bash
   VERSION=2.1.0
   gh release create v$VERSION dist/AirDrop-Compress-$VERSION-arm64.dmg dist/AirDrop-Compress-arm64.dmg \
     --title "AirDrop Compress $VERSION" --notes-file <(sed -n "/^## $VERSION/,/^## /p" CHANGELOG.md | sed '$d')
   ```
6. The website updates itself on push to `main` (see [Website deployment](DEPLOYMENT.md)). Its download button points to `releases/latest/download/AirDrop-Compress-arm64.dmg`, so it serves the new version as soon as the release is published.

Users are notified by the in-app update check within a day.
