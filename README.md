# AirDrop Compress

**Every photo and document you AirDrop to your Mac, made web-ready automatically.**

AirDrop Compress lives in your menu bar and watches your AirDrop folder:

- **Images** (HEIC, JPEG, PNG, TIFF, GIF, BMP, WebP, AVIF) → compressed **WebP**, **AVIF** or **JPEG**, sized and named for the web.
- **Documents** (PDF, Word, PowerPoint, Excel, RTF, ODT, HTML, CSV, EPUB, Outlook, ZIP, text, code, contacts…) → clean **Markdown**.
- **Anything else** → add a [plugin](docs/PLUGINS.md).

Results go to an `airdrop-compress` folder inside your AirDrop folder. **Your original files are never changed.**

## Install

1. Download the latest `AirDrop-Compress-x.y.z-arm64.dmg` from [Releases](https://github.com/najathi/airdrop-compress/releases). Builds are for Apple silicon; on an Intel Mac, [build from source](#build-from-source).
2. Open the `.dmg` and drag **AirDrop Compress** to **Applications**.
3. Open it from Applications. The app isn't notarised yet, so the first time macOS says it can't verify it. Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway**. The disk image includes an illustrated **How to open** guide. Or, in Terminal: `xattr -dr com.apple.quarantine "/Applications/AirDrop Compress.app"`.
4. When macOS asks whether AirDrop Compress may access your Desktop or Downloads folder, click **Allow**.

An icon appears in the menu bar. The app starts at login (you can turn this off) and has no Dock icon.

**Requirements:** macOS 12 Monterey or later.

## Using it

AirDrop something to your Mac. It's converted within a few seconds and you get a notification such as *"5 images: 12.4 MB → 3.1 MB (75% smaller)"*.

The **menu bar icon** shows the status (watching, busy, paused, or needs attention) and has **Pause/Resume**, **Open Dashboard**, **Open Output Folder** and **Convert Files…**.

The **Dashboard** shows what happened to every file (done, skipped and why, or failed and why), today's savings, and a drop zone for converting any file on demand.

## Choosing an image format

No single format is best for every image, so you choose. The **Compare formats** tool (under Images) shows how big one of your own images would be in each format with your current settings.

| Format | Best for | Watch out for |
|---|---|---|
| **WebP** (default) | General web use. All modern browsers support it, files are 25–35% smaller than JPEG, and it handles transparency and animation. | A few older apps, email clients and print services. |
| **AVIF** | The smallest photos, often 20–50% smaller than WebP. | Slower to encode; needs Safari 16+ / iOS 16+; some CMSs and social sites reject it. |
| **JPEG** | Maximum compatibility: email, Office, marketplaces, print. | Largest files; no transparency or animation. |
| **Auto** | Not knowing where images will end up. It encodes each format and keeps the smallest. | About three times slower; the file type varies from image to image. |

The other image options follow [Google's image best practices](https://developers.google.com/search/docs/appearance/google-images) and [web.dev guidance](https://web.dev/learn/images):

- **Quality** per format (defaults WebP 80, AVIF 60, JPEG 82), and **compression effort** (fast / balanced / smallest).
- **Target file size.** Lowers quality, never below 30, then shrinks the image until it fits, e.g. "under 200 KB".
- **Maximum size** (longest edge) and **responsive sizes**: extra `-480w`, `-800w`… copies for `srcset`.
- **Metadata.** Keep all, remove location (GPS), or remove all. The colour profile is always kept unless you convert to sRGB.
- **Convert to sRGB**, so colours match on every screen. iPhones shoot in Display P3.
- **SEO-friendly file names:** `IMG_1286 Beach Day.HEIC` → `img-1286-beach-day.webp`.
- **JPEG fallback**, for `<picture>` elements and platforms without WebP/AVIF support.
- **Lossless WebP for PNG graphics** (screenshots, logos), **progressive JPEG**, and **skip if larger**.

## Settings

Settings are grouped into **Images**, **Documents**, **General** and **Plugins**, and every change is saved immediately. They're stored in `~/Library/Application Support/AirDropCompress/settings.json`.

| General setting | Default | |
|---|---|---|
| AirDrop folder | Automatic | `~/Desktop/AirDrop` if it exists (for example, if you sort AirDrops there with a Folder Action), otherwise `~/Downloads`. |
| Output folder | `airdrop-compress` | A name inside the AirDrop folder, or any full path. |
| Only AirDrop files | On | Skips browser and app downloads (detected from macOS's download tag). |
| Notifications | On | One per batch. |
| Open at login | On | |
| Files at the same time | 2 | |
| Check for updates | On | Once a day, from GitHub releases. Nothing else is sent. |

**Housekeeping:** *Process files already in the folder* converts what's already there. *Clear history* lets files you receive again be converted again. *Reset* restores the defaults.

## Plugins

Plugins add file types or replace built-in conversions. They run in a **macOS sandbox**: a plugin can read only the file it's converting, can write only its own results, and has no internet access and can't run other programs unless you approve those permissions. A plugin stays off until you turn it on, and is switched off again if its code changes.

Install one under **Plugins → Install plugin…**. To build one, see the **[plugin guide](docs/PLUGINS.md)** and the example in [`examples/plugins/svg-minify`](examples/plugins/svg-minify).

## Updating and uninstalling

- **Update:** the app checks GitHub once a day and shows a banner when a new version is out. Download the new `.dmg` and drag the app to Applications again. Your settings, history and plugins are kept.
- **Uninstall:** **About → Uninstall…** removes the app, its login item, settings, history, plugins and log. Your original files and the output folder stay.

## Command line

The same engine runs without the menu bar app:

```bash
python -m airdrop_compress run                      # watch in the foreground
python -m airdrop_compress scan                     # convert what's already in the folder, then exit
python -m airdrop_compress settings                 # show the settings file
python -m airdrop_compress plugin validate <folder> # check a plugin
```

`./airdrop-compress install | enable | disable | status | logs | uninstall` runs it as a background LaunchAgent, as in version 1. Only one watcher (the app or the command line) runs at a time.

## Build from source

```bash
git clone https://github.com/najathi/airdrop-compress.git
cd airdrop-compress
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                    # run the tests
.venv/bin/python -m airdrop_compress gui      # run the app from source
packaging/build.sh                            # build dist/AirDrop Compress.app and the .dmg
```

For a signed and notarised build (no Gatekeeper warning), set `SIGN_IDENTITY` and `NOTARY_PROFILE`. The top of [`packaging/build.sh`](packaging/build.sh) explains how. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the code is organised.

## Troubleshooting

- **Nothing happens:** check the menu bar icon and the Dashboard banner. *"macOS is blocking access"* means you need to allow the app under **System Settings → Privacy & Security → Files and Folders** (or Full Disk Access). It continues by itself once allowed.
- **A file was skipped:** the Dashboard shows the reason, for example a browser download, a duplicate, an unsupported type such as Pages/Numbers/Keynote or video, or a scanned PDF with no text.
- **Log:** `~/Library/Logs/AirDropCompress/airdrop-compress.log` (or **About → Log → Show**).

## License

[MIT](LICENSE). Document conversion uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Image codecs are libwebp, libavif, libjpeg-turbo and libheif (via Pillow and pillow-heif).
