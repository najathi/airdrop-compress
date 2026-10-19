# User Guide

## How automatic processing works

```
iPhone ──AirDrop──▶ AirDrop folder ──▶ AirDrop Compress ──▶ airdrop-compress/
                    (~/Downloads or        detects, checks,        photo.webp
                     ~/Desktop/AirDrop)    converts                notes.md
```

1. **You receive a file.** macOS saves AirDropped files to `~/Downloads`. If you use a Folder Action (such as *airdropSorter*) that moves them to `~/Desktop/AirDrop`, AirDrop Compress watches that folder instead.
2. **The app notices it** within a second, using macOS file-system events. It also rescans the folder every 30 seconds as a safety net.
3. **It waits until the file is complete,** so large files and batches are never read half-written. Empty files are skipped.
4. **It checks where the file came from.** Files downloaded by a browser or another app (Chrome, Safari, Slack…) are skipped, so only AirDrop files are converted. You can turn this off.
5. **It checks for duplicates.** The same file is never converted twice, even under a different name.
6. **It converts the file:** images to WebP, AVIF or JPEG, documents to Markdown, or other types through an enabled plugin.
7. **It saves the result** to the output folder and adds a line to the Dashboard. One notification sums up each batch.

Only files that arrive **while the app is running** are converted. Files that were already in the folder are left alone. To convert those, use **General → Process files already in the folder**.

**Your originals are never modified, moved or deleted.**

## The menu bar icon

| Icon | Meaning |
|---|---|
| Down-arrow circle | Watching for AirDrop files |
| Filled circle | Converting right now |
| Pause circle | Paused |
| Exclamation circle | Needs attention: open the Dashboard |

The menu shows the status and today's savings, and has **Pause / Resume**, **Open Dashboard…**, **Open Output Folder**, **Convert Files…** and **Quit**.

Closing the window doesn't quit the app; it keeps working in the menu bar. **Quit** stops it until you open it again or log in again.

## The Dashboard

- **Status card:** what the app is doing, the folder it watches, the **Output folder** button and **Pause / Resume**.
- **Statistics:** files processed and space saved today and in total. Savings count images only.
- **Settings summary:** your current image format and quality, the document setting and the active plugins. Click one to change it.
- **Drop zone:** drop any files here, or click **choose files…**, to convert them now. This works for files anywhere on your Mac, not just AirDrops.
- **Activity:** every file, with its result:
  - **Done:** the files it created (click a name to show it in Finder) and the size before and after.
  - **Skipped:** why, for example *Downloaded by Chrome*, *Already converted*, *No converter for .mov files* or *The file is empty*.
  - **Failed:** a plain-language reason, for example *Not a valid image, or the file is damaged*.

## Where converted files go

By default, results go to a folder called **`airdrop-compress`** inside the AirDrop folder:

- `~/Downloads/airdrop-compress/`, or
- `~/Desktop/AirDrop/airdrop-compress/` if you use that folder.

To change it, go to **General → Output folder** and enter:

- **a folder name** (for example `Web Images`), created inside the AirDrop folder; or
- **a full path** (for example `~/Pictures/Web` or `/Volumes/Work/Inbox`).

The output folder can't be the AirDrop folder itself, because results would be picked up and converted again.

**File names:** the result keeps the original name with a new extension (`IMG_1286.HEIC` → `IMG_1286.webp`). If that name is taken, a number is added (`IMG_1286-1.webp`); existing files are never overwritten. Very long names are shortened to fit macOS's limit. With **SEO-friendly file names** on, image names become lowercase and hyphenated (`img-1286.webp`).

**Upgrading from version 1:** an existing `Image Compressed` folder is renamed to `airdrop-compress` automatically.

## Settings

Settings are saved immediately and kept across restarts. The file is `~/Library/Application Support/AirDropCompress/settings.json`. Each page has a **Reset** option.

### Images

| Setting | Default | What it does |
|---|---|---|
| Convert images | On | Turn image conversion off entirely. |
| Output format | WebP | **Auto**, **WebP**, **AVIF** or **JPEG**. See [Formats](FORMATS.md). |
| Quality | WebP 80, AVIF 60, JPEG 82 | 1–100 for each format. |
| Compression effort | Balanced | Fast, Balanced or Smallest (slowest). |
| Lossless for PNG graphics | Off | Pixel-perfect WebP for screenshots and logos. |
| Progressive JPEG | On | JPEGs load blurry first, then sharpen. |
| Target file size | Off | Fit each image under a size, such as 200 KB. |
| Skip if the result is larger | Off | Keep well-compressed JPEG/PNG/WebP originals as they are. |
| Maximum size | Original | Limit the longest edge, for example 1920 px. |
| Responsive sizes | None | Extra smaller copies such as `photo-800w.webp`. |
| Photo details (EXIF) | Keep all | Keep all, Remove location, or Remove all. |
| Colour | Keep profile | Keep the colour profile, or convert to sRGB. |
| SEO-friendly file names | Off | `IMG_1286 Beach.HEIC` → `img-1286-beach.webp`. |
| Also save a JPEG fallback | Off | Adds a `.jpg` next to WebP/AVIF results. |

**Compare formats** (bottom of the Images page) shows how big one of your images would be as WebP, AVIF and JPEG with the current settings. Nothing is saved. Click **Use** to switch to a format.

### Documents

| Setting | Default | |
|---|---|---|
| Convert documents | On | |
| Largest document to convert | 100 MB | Bigger files are skipped. |

### General

| Setting | Default | |
|---|---|---|
| AirDrop folder | Automatic | Or choose any folder. |
| Output folder | `airdrop-compress` | See [Where converted files go](#where-converted-files-go). |
| Only AirDrop files | On | Skip browser and app downloads. |
| Notifications | On | One per batch. |
| Open at login | On | Starts quietly in the menu bar. |
| Files at the same time | 2 | 1–4 files converted in parallel. |
| Check for updates | On | Once a day, from GitHub. |

**Housekeeping:**

- **Process files already in the folder** converts what's already there.
- **Clear history** forgets which files were converted, so files received again are converted again. Your files aren't deleted.
- **Reset all** restores the defaults. Plugins stay installed.

## Pausing and quitting

- **Pause** (Dashboard or menu bar) stops processing. Files that arrive while paused are **not** converted when you resume. Use *Process files already in the folder* for those.
- **Quit** stops the app. It starts again at your next login if *Open at login* is on.

## After restarting your Mac

With **Open at login** on, AirDrop Compress starts in the background when you log in and continues watching. Files received while the Mac was off or the app wasn't running aren't converted automatically; use *Process files already in the folder*.

## Privacy

- Everything happens on your Mac. Files are never uploaded.
- The only network request is the optional daily update check to `api.github.com`.
- The conversion history stores file names and fingerprints (SHA-256) in `~/Library/Application Support/AirDropCompress`, which only your user account can read.
- AirDrop itself: set **AirDrop → Contacts Only** in Control Center if you don't want strangers nearby to be able to send you files.
