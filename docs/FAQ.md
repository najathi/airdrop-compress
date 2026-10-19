# Frequently asked questions

### Is AirDrop Compress free?
Yes. It's free and open source under the MIT licence.

### Does it change or delete my original files?
No. Originals are only ever read. Results are saved as new files in the output folder, and existing files there are never overwritten.

### Does it upload my files anywhere?
No. Everything is processed on your Mac. The only network request is the optional daily update check to GitHub, which you can turn off in **General**.

### Which Macs does it run on?
macOS 12 Monterey or later. The download is built for Apple silicon (M1 and later). On an Intel Mac you can [build it from source](INSTALL.md#build-from-source).

### Why does macOS say it can't verify the app?
The app isn't notarised by Apple yet. Confirm once with **Open Anyway**. See [The first launch](INSTALL.md#the-first-launch).

### Does it only work with AirDrop?
It watches the folder AirDrop saves to and, by default, converts only files that arrived by AirDrop. You can also drop any file on the Dashboard (or use **Convert Files…** in the menu bar) to convert it, and turn off **Only AirDrop files** to convert everything that arrives in that folder.

### Where do the converted files go?
To an `airdrop-compress` folder inside your AirDrop folder, unless you choose another one in **General → Output folder**. See [Where converted files go](USER_GUIDE.md#where-converted-files-go).

### Which format should I choose: WebP, AVIF or JPEG?
WebP for general web use, AVIF for the smallest photos where it's supported, and JPEG when compatibility matters most. **Auto** picks the smallest for each image. The **Compare formats** tool shows the difference for your own images. See [Formats](FORMATS.md#choosing-a-format).

### Will compression reduce the quality?
WebP, AVIF and JPEG are lossy formats, but at the default quality settings the difference is very hard to see in photos, while files are typically 60–80% smaller than iPhone HEIC originals. You can raise the quality, or use lossless WebP for PNG graphics.

### How much space will I save?
It depends on the image. Photos from an iPhone usually shrink by about 60–75% at the default settings. Screenshots, documents and already-compressed JPEGs save less. The Dashboard shows the real numbers.

### Does it keep the date and location of my photos?
By default it keeps all photo details. Choose **Remove location** to drop GPS, or **Remove all** to drop all metadata, under Images → Photo details.

### What happens if I receive the same photo twice?
It's converted once. The app recognises files by their content, not their name.

### What if two different files have the same name?
The second result gets a number: `IMG_1286.webp`, then `IMG_1286-1.webp`.

### Can it convert Pages, Numbers or Keynote files?
Not yet. Export them to PDF, Word or Excel first, or build a plugin.

### Can it read text from scanned PDFs?
Not built in. Scanned PDFs contain images rather than text and are skipped. An OCR plugin could add this.

### Does it keep running after I restart my Mac?
Yes, if **Open at login** is on (the default). It starts in the menu bar when you log in.

### How do I stop it?
Click the menu bar icon and choose **Pause** to stop processing, or **Quit** to close the app.

### Can I run it without the menu bar app?
Yes. There's a command-line mode for scripting and servers. See [Install → Command line only](INSTALL.md#command-line-only-no-menu-bar-app).

### Are plugins safe?
Plugins run in a macOS sandbox: they can only read the file they're converting and write their own results. They have no internet access and can't run other programs unless you approve that, and they can't read your clipboard or your other files. They stay off until you approve them. See the [Plugin guide](PLUGINS.md#security-model).

### Can you build a custom version for my business?
Yes. Use **Let's build together** in the app (About) or on the website to describe what you need.

### How do I report a bug or ask for a feature?
Open an issue on [GitHub](https://github.com/najathi/airdrop-compress/issues/new/choose). Report security problems privately as described in [SECURITY.md](../SECURITY.md).
