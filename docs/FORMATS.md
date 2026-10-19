# Supported formats and compression options

## At a glance

| You receive | You get | Converted by |
|---|---|---|
| HEIC, HEIF, JPEG, PNG, TIFF, GIF, BMP, WebP, AVIF | WebP, AVIF or JPEG (your choice), plus optional extras | Pillow, pillow-heif, libwebp, libavif |
| PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx, .xls), HTML, CSV, JSON, EPUB, Jupyter (.ipynb), Outlook (.msg), ZIP, .txt, .md | Markdown (.md) | Microsoft MarkItDown, in a sandbox |
| Old Word (.doc), RTF, OpenDocument (.odt), Safari web archives, WordML | Markdown (.md) | macOS `textutil`, then MarkItDown |
| Code and config (.py, .js, .ts, .swift, .sql, .yaml, .json lines, .sh, …), logs, contacts (.vcf), calendar invites (.ics) | Markdown with the content in a code block | Built in, as plain text |
| Anything a plugin supports (for example .svg with the example plugin) | Whatever the plugin creates | The plugin, in a sandbox |

**Not supported:** Apple Pages, Numbers and Keynote files, videos, audio, ProRAW (`.DNG`), and scanned PDFs that contain no text (they'd need OCR, which a plugin could add). These are listed as *Skipped* on the Dashboard with the reason.

## Images

### Choosing a format

No single format is best for every image, so you choose, or let **Auto** decide per image.

| Format | Best for | Watch out for |
|---|---|---|
| **WebP** (default) | General web use. Supported by all modern browsers; typically 25–35% smaller than JPEG at the same visual quality; handles transparency and animation. | Some older apps, email clients and print services. |
| **AVIF** | The smallest photos, often 20–50% smaller than WebP. | Slower to encode; needs Safari 16+ / iOS 16+; some CMSs and social sites reject it. |
| **JPEG** | Maximum compatibility: email, Office, marketplaces, print. | Largest files; no transparency (it's flattened onto white) and no animation. |
| **Auto** | Not knowing where images will be used. Encodes WebP, AVIF and JPEG (WebP and AVIF only for images with transparency) and keeps the smallest. | About three times slower; the file type can vary from image to image. |

The **Compare formats** tool on the Images page shows the real numbers for one of your own images.

### What happens to every image

- **Rotation** from the iPhone is applied to the pixels, so nothing appears sideways.
- **Transparency** is kept (WebP and AVIF). **Animated GIFs** stay animated as WebP or AVIF; if you chose JPEG or Auto, animations are saved as WebP.
- **Colour profile** (for example iPhone's Display P3) is kept, unless you choose *Convert to sRGB*.
- **Metadata** follows your *Photo details* setting.
- Results are written in one step, so you never see a half-written file.

### Compression options

| Option | Details |
|---|---|
| **Quality** | 1–100 per format. Suggested ranges: WebP 75–85, AVIF 50–65, JPEG 80–85 (90+ keeps full colour detail). |
| **Compression effort** | *Fast*: quicker, slightly larger. *Balanced*: recommended. *Smallest*: slowest; matters most for AVIF. |
| **Target file size** | Lowers the quality until the image fits (never below 30), then shrinks the dimensions if needed. If it still can't fit, the closest result is kept and the Dashboard says so. |
| **Maximum size** | Limits the longest edge (for example 1920 px). Smaller images aren't enlarged. Animated images keep their size. |
| **Responsive sizes** | Extra copies at fixed widths (320–1920 px) named `name-800w.webp` and so on, for HTML `srcset`. Widths larger than the image are skipped. |
| **Lossless for PNG graphics** | WebP only: PNG sources are saved pixel-perfect, which suits screenshots, logos and text. |
| **Progressive JPEG** | On by default. |
| **Skip if the result is larger** | For JPEG, PNG, GIF, WebP and AVIF originals only. HEIC, TIFF and BMP are always converted, because browsers can't show them. |
| **Photo details** | *Keep all*, *Remove location* (removes GPS and XMP), or *Remove all* (keeps only the colour profile). |
| **Convert to sRGB** | Converts colours to sRGB and drops the profile, so colours match on every screen. |
| **SEO-friendly file names** | Lowercase, hyphenated, ASCII-only names, as Google recommends. |
| **JPEG fallback** | Adds a `.jpg` next to WebP/AVIF results, for `<picture>` fallbacks. |

### Limits

- Images above about 178 megapixels are refused as unsafe (*The image is too large to process safely*).
- WebP can't exceed 16,383 px on a side; larger images are scaled down to fit.

## Documents

Documents become **Markdown**: plain text with headings, lists, tables and links, which opens in any text editor and is easy to search.

| Source | Result |
|---|---|
| PDF | The text, in reading order. Scanned PDFs contain no text and are skipped. |
| Word (.docx) | Headings, bold and italics, lists and tables. |
| PowerPoint | One section per slide, with its text and tables. |
| Excel (.xlsx, .xls) | One Markdown table per sheet. |
| CSV | A Markdown table. |
| HTML, web archives | Headings, links, lists and tables. |
| EPUB | The book's text. |
| ZIP | One section per file inside it. |
| Outlook .msg | Headers and body. |
| Code, config, contacts, calendar invites | The original text in a code block under the file name. |

Converted text is tidied (no trailing spaces or runs of blank lines) and saved as UTF-8.

### Safety limits for documents

- Documents larger than the **Largest document** setting (default 100 MB) are skipped.
- ZIP-based files (`.zip`, `.docx`, `.xlsx`, `.pptx`, `.epub`, `.odt`) that would expand to more than **300 MB**, contain more than 5,000 files, or are compressed suspiciously well are skipped as unsafe ("zip bombs").
- A conversion that takes longer than **5 minutes** is stopped.
- Conversion runs in a **sandboxed process** that can read only the document itself and can't use the network. See [Security](../SECURITY.md).

## Plugins

Plugins can add new types or take over existing ones. See the [Plugin guide](PLUGINS.md).
