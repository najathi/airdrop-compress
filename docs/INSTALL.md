# Installing AirDrop Compress

## Requirements

| | |
|---|---|
| **macOS** | 12 Monterey or later (tested on the current macOS release) |
| **Mac** | Apple silicon (M1 or later) for the ready-made download. On an Intel Mac, [build from source](#build-from-source). |
| **Disk space** | About 200 MB for the app |
| **Internet** | Not required. The optional daily update check contacts GitHub. |

## Install the app

1. Download **AirDrop-Compress-arm64.dmg** from the [latest release](https://github.com/najathi/airdrop-compress/releases/latest).
2. Open the `.dmg` and drag **AirDrop Compress** onto **Applications**.
3. Open AirDrop Compress from your Applications folder.

### The first launch

The app isn't notarised by Apple yet, so macOS asks you to confirm the first time. You only do this once.

**macOS 15 Sequoia and later**

1. Open the app. macOS says *"AirDrop Compress" Not Opened*. Click **Done**, not *Move to Trash*.
2. Open **System Settings → Privacy & Security**, scroll down to **Security**, and click **Open Anyway** next to *"AirDrop Compress" was blocked*.
3. Click **Open Anyway** again, then enter your password or use Touch ID.

**macOS 12–14:** in Applications, right-click (or Control-click) AirDrop Compress, choose **Open**, then click **Open**.

**Using Terminal instead (any macOS):**

```bash
xattr -dr com.apple.quarantine "/Applications/AirDrop Compress.app"
```

This removes the "downloaded from the internet" flag from this one app. Only do this for apps you trust.

The disk image also contains an illustrated **How to open** guide with these steps.

### Allow access to your AirDrop folder

When the app first runs, macOS asks whether AirDrop Compress may access your **Desktop** or **Downloads** folder. Click **Allow**.

If you clicked *Don't Allow*, or no prompt appeared, open **System Settings → Privacy & Security → Files and Folders**, find AirDrop Compress and turn on the folder. (Or add it under **Full Disk Access**.) The app checks again every 10 seconds and continues on its own.

## After installing

- An icon appears in the **menu bar**. The app has no Dock icon.
- It's set to **open at login**. You can turn that off in **General**.
- AirDrop something to your Mac to try it. See the [User Guide](USER_GUIDE.md).

## Updating

Once a day the app checks GitHub for a new version (you can turn this off in **General**). When there's one, a banner appears on the Dashboard and in **About**.

1. Click **Download**, or get the new `.dmg` from [Releases](https://github.com/najathi/airdrop-compress/releases).
2. Quit AirDrop Compress from its menu bar icon.
3. Drag the new version onto Applications and choose **Replace**.

Your settings, history and plugins are kept. Updates are never installed automatically.

## Uninstalling

Open the app, go to **About → Uninstall…** and confirm. This removes:

- the app (moved to the Trash) and its login item;
- settings, conversion history and installed plugins (`~/Library/Application Support/AirDropCompress`);
- the log (`~/Library/Logs/AirDropCompress`).

**Your original files and everything in the output folder are kept.**

To uninstall by hand, quit the app, then delete the app, the two folders above, and `~/Library/LaunchAgents/com.najathi.airdropcompress.login.plist`.

## Build from source

You need Python 3.10 or later (from [python.org](https://www.python.org/downloads/macos/) or Homebrew).

```bash
git clone https://github.com/najathi/airdrop-compress.git
cd airdrop-compress
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m airdrop_compress gui     # run the menu bar app from source
packaging/build.sh                            # or build the .app and .dmg for this Mac
```

The build is for the Mac you build on, so building on an Intel Mac gives an Intel app. See [Releasing](RELEASING.md) for signing and notarisation.

### Command line only (no menu bar app)

The same engine runs headless:

```bash
.venv/bin/python -m airdrop_compress run     # watch in the foreground
./airdrop-compress install                    # or as a background LaunchAgent
```

`./airdrop-compress enable | disable | status | logs | scan | uninstall` manages that background service. It shares the app's settings file. Don't run it and the app at the same time; only one of them processes files.
