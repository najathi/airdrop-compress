# Troubleshooting

Start with the **Dashboard**. Every file is listed with what happened to it, and banners at the top explain problems that need your attention.

## Nothing happens when I AirDrop a file

1. **Is the app running?** Look for its icon in the menu bar. If it isn't there, open AirDrop Compress from Applications.
2. **Is it paused?** The menu bar icon shows a pause symbol. Click it and choose **Resume**.
3. **Is it watching the right folder?** The Dashboard shows the folder under the status. AirDrop saves to `~/Downloads`; if your files end up somewhere else (for example `~/Desktop/AirDrop`), choose that folder under **General → AirDrop folder**.
4. **Is a banner showing?**
   - *macOS is blocking access to your AirDrop folder*: click **Open Privacy settings** and allow AirDrop Compress under **Files and Folders** (or **Full Disk Access**). It continues by itself within 10 seconds.
   - *Another copy is running*: AirDrop Compress or the command-line service is already running somewhere. Quit the other one; the app takes over within a few seconds.
   - *The command-line version is still running*: click **Switch to the app**.
5. **Was the file skipped?** Check the **Skipped** filter in Activity for the reason.

## A file was skipped

| Message | What it means / what to do |
|---|---|
| Downloaded by Chrome (or another app), not AirDrop | **Only AirDrop files** is on. Turn it off in General, or drop the file on the Dashboard to convert it anyway. |
| Already converted to … | The same file (same content) was converted before. Delete the earlier result or use **General → Clear history** to convert it again. |
| No converter for .xyz files | The type isn't supported. See [Formats](FORMATS.md), or install a plugin. |
| The file is empty | The file has no content. |
| Removed before it could be converted | The file was moved or deleted (for example by a Folder Action) before it finished arriving. |
| Larger than 100 MB | Raise **Documents → Largest document to convert**. |
| Expands to … MB when unpacked - skipped for safety | The archive or Office file would expand to an unsafe size. |
| No text found - a scanned or image-only document? | The PDF contains pictures of text, not text. |
| The original … is already smaller than the … result | **Skip if the result is larger** is on, and the original is already well compressed. |

## A file failed

| Message | What to do |
|---|---|
| Not a valid image, or the file is damaged | The file isn't really an image of that type, or it's corrupt. Try sending it again. |
| The image is incomplete or damaged | The transfer was probably cut off. Send it again. |
| The image is too large to process safely | The image is over about 178 megapixels. |
| This file couldn't be read as a document | The document is damaged, password-protected, or not what its extension says. |
| Took longer than 5 minutes to convert and was stopped | Very large or complex document. Try splitting it. |
| macOS didn't allow reading or saving this file | Check folder permissions (see above) and that the output folder is writable. |

## Images look wrong

- **Colours look duller in some apps:** turn on **Convert to sRGB** (Images → Metadata & colour).
- **Files are too big:** lower the quality, set a **Maximum size**, try **AVIF**, or set a **Target file size**. Use **Compare formats** to see the effect.
- **Text in screenshots looks blurry:** turn on **Lossless for PNG graphics**.
- **The output is larger than the original:** this can happen with JPEGs that are already highly compressed. Turn on **Skip if the result is larger**.

## The app doesn't start at login

Check **General → Open at login** is on. In **System Settings → General → Login Items & Extensions**, make sure *AirDrop Compress* is allowed to run in the background.

## "AirDrop Compress" can't be opened / is damaged

See [The first launch](INSTALL.md#the-first-launch). If macOS says the app is *damaged*, the download was probably interrupted. Download it again, or run:

```bash
xattr -dr com.apple.quarantine "/Applications/AirDrop Compress.app"
```

## Plugins

- **Changed – approve again:** the plugin's files changed since you approved it. If you updated it yourself, click **Review…** and approve it again.
- **Not compatible:** the plugin needs a newer AirDrop Compress or a different plugin API version.
- **Invalid:** its `plugin.json` has a problem, listed on the card.
- **Sandbox unavailable:** your macOS doesn't provide `sandbox-exec`, so plugins are disabled for safety.

## Logs and reporting a problem

- Log: `~/Library/Logs/AirDropCompress/airdrop-compress.log` (**About → Log → Show**).
- Report bugs on [GitHub Issues](https://github.com/najathi/airdrop-compress/issues/new/choose). Include your macOS version, the app version (in About), and the relevant lines from the log. **Remove any file names you don't want to share.**
- For security problems, follow [SECURITY.md](../SECURITY.md) instead of opening a public issue.
