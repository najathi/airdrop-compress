# AirDrop Compress (macOS)

Watches your AirDrop folder and processes every file you receive:

- **Images** (HEIC, HEIF, JPEG, PNG, TIFF, GIF, BMP, AVIF) → a compressed **WebP** copy.
- **Documents** (PDF, Word, PowerPoint, Excel, RTF, ODT, HTML, CSV, JSON, EPUB, Outlook `.msg`, ZIP, plain text, code, contact cards…) → a **Markdown** (`.md`) copy.

Everything is saved to one `airdrop-compress` folder inside the AirDrop folder:

```
~/Downloads/airdrop-compress/            # default: AirDrop saves to Downloads
~/Desktop/AirDrop/airdrop-compress/      # if ~/Desktop/AirDrop exists (see below)
```

If you used an earlier version, its `Image Compressed` folder is renamed to `airdrop-compress` automatically. Your existing WebP files move with it.

AirDrop always saves to `~/Downloads`. Some people use a Folder Action, such as the popular `airdropSorter` script, to move AirDropped files from Downloads into `~/Desktop/AirDrop`. If that folder exists, the tool watches it instead of Downloads. To pick a folder yourself, change `WATCH_DIR` (see Settings).

Your original files are never changed. The tool runs in the background, starts when you log in, and can be turned on or off with one command.

## Install (one time)

Requires Python 3.10+ (`python3 --version`).

```bash
git clone https://github.com/najathi/airdrop-compress.git
cd airdrop-compress
./airdrop-compress install
```

This command:
1. Creates a virtual environment in `.venv` and installs the libraries from `requirements.txt` (Pillow, pillow-heif, watchdog, and Microsoft's [MarkItDown](https://github.com/microsoft/markitdown) for documents).
2. Installs a LaunchAgent (`~/Library/LaunchAgents/com.<you>.airdrop-compress.plist`) so the tool starts at every login.
3. Starts it right away.

### Permission for the AirDrop folder

macOS protects the Desktop and Downloads folders. The first time the service runs, you may get a "Python would like to access files in your Desktop folder" prompt. Click **Allow**. If no prompt appears, or the log says *"macOS is blocking access"*, run:

```bash
./airdrop-compress permissions
```

It prints the exact Python program to allow and opens **System Settings → Privacy & Security → Full Disk Access**. Click **+**, press **⌘⇧G**, paste the path and turn it on. The service checks again every 30 seconds, so you don't need to restart it.

## Turn it on and off

| Command | What it does |
|---|---|
| `./airdrop-compress disable` | Stops watching. It stays off after restarts and logins. |
| `./airdrop-compress enable` | Starts watching again, now and at every login. |
| `./airdrop-compress status` | Shows Running, Disabled, or Not installed, plus the last log lines. |
| `./airdrop-compress logs` | Follows the live log (Ctrl+C to quit). |
| `./airdrop-compress restart` | Restarts the service. Use this after you change settings. |
| `./airdrop-compress scan` | One-off: converts files already in the AirDrop folder (skips any it converted before). |
| `./airdrop-compress run` | Runs in the terminal instead of the background (Ctrl+C to stop). |
| `./airdrop-compress uninstall` | Removes the LaunchAgent. Your originals and the `airdrop-compress` folder stay. |

Tip: to run these from any folder, add an alias to `~/.zshrc`:
`alias airdrop-compress="/path/to/airdrop-compress/airdrop-compress"`

## How it works

- **Detection:** it gets file-system events (FSEvents through `watchdog`) for the AirDrop folder. It also rescans the folder every 30 seconds in case an event is missed. Only files that arrive while the service is running count as new. A file counts as new when its name and inode (a file's internal ID) don't match what was in the folder at startup. File dates aren't used, because AirDrop sets them to when the photo was taken.
- **Waiting for complete files:** before converting, it waits until the file's size stops changing, so large or batched AirDrops are never read half-written. It processes two files at a time and queues the rest.
- **AirDrop vs. web downloads:** macOS tags every received file with a quarantine flag naming the app it came from. AirDrop files are tagged `sharingd`. Browser and app downloads are tagged with that app's name (Chrome, Firefox, Slack…), and those are skipped. Untagged files, such as ones you copy into the folder yourself, are treated as AirDrop.
- **Image conversion:**
  - Applies the iPhone rotation to the pixels, so photos aren't sideways.
  - Keeps transparency and keeps animated GIFs animated.
  - Keeps EXIF (date, camera, GPS) and the colour profile.
  - Saves as WebP at quality 80 with the strongest compression method. Files are written atomically, so you never see a half-written output file.
- **Document conversion:**

  | Type | How it's converted |
  |---|---|
  | PDF, Word (`.docx`), PowerPoint, Excel (`.xlsx`, `.xls`), HTML, CSV, JSON, EPUB, Jupyter, Outlook `.msg`, ZIP, `.txt`/`.md` | [MarkItDown](https://github.com/microsoft/markitdown). Headings, lists and tables become Markdown, slides become sections, and spreadsheets and CSVs become tables. A ZIP gets one section per file inside it. |
  | Old Word (`.doc`), RTF, OpenDocument (`.odt`), Safari `.webarchive` | macOS's built-in `textutil` converts it to HTML, then MarkItDown converts that. |
  | Code and config files (`.py`, `.js`, `.sql`, `.yaml`…), logs, contacts (`.vcf`), calendar invites (`.ics`) | Wrapped in a fenced code block under the file name. |

  The Markdown is tidied (no trailing spaces or runs of blank lines). It's plain UTF-8 text, so it stays readable in any editor.
- **No duplicates:** each file is identified by a SHA-256 hash of its content and recorded in `~/Library/Application Support/AirDropCompress/processed.json`. The same file isn't converted twice, even under a different name. If you delete an output file, receiving that file again re-creates it. If two different files share a name (`IMG_1.HEIC` and `IMG_1.JPG`, or `notes.pdf` and `notes.docx`), the second gets a `-1` suffix.
- **Notifications:** after each batch you get one macOS notification, e.g. "5 images: 12.4 MB → 3.1 MB (75% smaller). 2 documents converted to Markdown".

## Settings

Edit the top of `airdrop_compress.py`, then run `./airdrop-compress restart`:

| Setting | Default | Meaning |
|---|---|---|
| `WEBP_QUALITY` | `80` | 0–100. Higher means better quality and bigger files. 75–85 is visually lossless for photos. |
| `MAX_DIMENSION` | `None` | For example, `3000` shrinks the long edge to 3000 px for much smaller files. |
| `KEEP_METADATA` | `True` | Set to `False` to strip EXIF, including GPS location. |
| `CONVERT_DOCUMENTS` | `True` | Set to `False` to only process images. |
| `MAX_DOCUMENT_MB` | `100` | Documents bigger than this are skipped. |
| `SKIP_WEB_DOWNLOADS` | `True` | Set to `False` to process every new file in the folder. |
| `NOTIFY` | `True` | Batch notifications on or off. |
| `WORKERS` | `2` | How many files are processed at the same time. |

To watch a different folder, change `WATCH_DIR` (for example back to `~/Downloads` if you stop using the Folder Action).

## Files

```
airdrop_compress.py   the watcher/converter
airdrop-compress      control script (install / enable / disable / status / logs ...)
requirements.txt      Python libraries
~/Library/Logs/AirDropCompress/airdrop-compress.log         log
~/Library/Application Support/AirDropCompress/processed.json  record of converted files
```

## Troubleshooting

- **Nothing happens:** run `./airdrop-compress status`, then `./airdrop-compress logs`. A *"blocking access"* message means the folder permission is missing (see above).
- **An old photo wasn't converted:** only files that arrive after the service starts are processed. Use `./airdrop-compress scan` to backfill.
- **A file was skipped:** the log says why for each one. It might have no converter (for example videos, ProRAW `.DNG`, or Apple Pages/Numbers/Keynote files), it might be a scanned PDF with no text in it, or it might have been downloaded by a browser.
