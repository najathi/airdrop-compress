# AirDrop → WebP Auto-Compressor (macOS)

Watches your AirDrop folder. Each image you receive (HEIC, HEIF, JPEG, PNG, TIFF, GIF, BMP or AVIF) gets a compressed WebP copy saved to an `Image Compressed` folder inside it:

```
~/Downloads/Image Compressed/            # default: AirDrop saves to Downloads
~/Desktop/AirDrop/Image Compressed/      # if ~/Desktop/AirDrop exists (see below)
```

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
1. Creates a virtual environment in `.venv` and installs the libraries from `requirements.txt` (Pillow, pillow-heif, watchdog).
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
| `./airdrop-compress scan` | One-off: converts images already in the AirDrop folder (skips any it converted before). |
| `./airdrop-compress run` | Runs in the terminal instead of the background (Ctrl+C to stop). |
| `./airdrop-compress uninstall` | Removes the LaunchAgent. Your originals and `Image Compressed` stay. |

Tip: to run these from any folder, add an alias to `~/.zshrc`:
`alias airdrop-compress="/path/to/airdrop-compress/airdrop-compress"`

## How it works

- **Detection:** it gets file-system events (FSEvents through `watchdog`) for the AirDrop folder. It also rescans the folder every 30 seconds in case an event is missed. Only files that arrive while the service is running count as new. A file counts as new when its name and inode (a file's internal ID) don't match what was in the folder at startup. File dates aren't used, because AirDrop sets them to when the photo was taken.
- **Waiting for complete files:** before converting, it waits until the file's size stops changing, so large or batched AirDrops are never read half-written. It converts two images at a time and queues the rest.
- **AirDrop vs. web downloads:** macOS tags every received file with a quarantine flag naming the app it came from. AirDrop files are tagged `sharingd`. Browser and app downloads are tagged with that app's name (Chrome, Firefox, Slack…), and those are skipped. Untagged images, such as ones you copy into the folder yourself, are treated as AirDrop.
- **Conversion:**
  - Applies the iPhone rotation to the pixels, so photos aren't sideways.
  - Keeps transparency and keeps animated GIFs animated.
  - Keeps EXIF (date, camera, GPS) and the colour profile.
  - Saves as WebP at quality 80 with the strongest compression method. Files are written atomically, so you never see a broken `.webp`.
- **No duplicates:** each image is identified by a SHA-256 hash of its content and recorded in `~/Library/Application Support/AirDropCompress/processed.json`. The same photo isn't converted twice, even under a different name. If you delete a WebP, receiving that photo again re-creates it. If two different files share a name (`IMG_1.HEIC` and `IMG_1.JPG`), the second becomes `IMG_1-1.webp`.
- **Notifications:** after each batch you get one macOS notification, e.g. "5 images: 12.4 MB → 3.1 MB (75% smaller)".

## Settings

Edit the top of `airdrop_compress.py`, then run `./airdrop-compress restart`:

| Setting | Default | Meaning |
|---|---|---|
| `WEBP_QUALITY` | `80` | 0–100. Higher means better quality and bigger files. 75–85 is visually lossless for photos. |
| `MAX_DIMENSION` | `None` | For example, `3000` shrinks the long edge to 3000 px for much smaller files. |
| `KEEP_METADATA` | `True` | Set to `False` to strip EXIF, including GPS location. |
| `SKIP_WEB_DOWNLOADS` | `True` | Set to `False` to convert every new image in the folder. |
| `NOTIFY` | `True` | Batch notifications on or off. |
| `WORKERS` | `2` | How many images are converted at the same time. |

To watch a different folder, change `WATCH_DIR` (for example back to `~/Downloads` if you stop using the Folder Action).

## Files

```
airdrop_compress.py   the watcher/converter
airdrop-compress      control script (install / enable / disable / status / logs ...)
requirements.txt      Python libraries
~/Library/Logs/AirDropCompress/airdrop-compress.log         log
~/Library/Application Support/AirDropCompress/processed.json  record of converted images
```

## Troubleshooting

- **Nothing happens:** run `./airdrop-compress status`, then `./airdrop-compress logs`. A *"blocking access"* message means the folder permission is missing (see above).
- **An old photo wasn't converted:** only files that arrive after the service starts are processed. Use `./airdrop-compress scan` to backfill.
- **ProRAW (`.DNG`) and videos** are ignored. Pillow can't read DNG, and videos aren't images.
