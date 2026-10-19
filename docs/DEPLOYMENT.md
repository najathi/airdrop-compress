# Website deployment

The website is a static site in [`site/`](../site) (landing page, styles, images). The documentation pages are generated from the Markdown files in [`docs/`](.) and the root of the repository. It is hosted on **GitHub Pages**:

**https://najathi.github.io/airdrop-compress/**

## How it deploys

`.github/workflows/pages.yml` runs on every push to `main` that touches `site/`, `docs/`, the root Markdown files, or the app version. It can also be run by hand from the *Actions* tab. It:

1. sets up Python and installs `markdown`;
2. runs `python site/build.py`, which:
   - copies `site/` to `_site/`;
   - fills in the version, download URL and site URL;
   - renders each documentation page (`docs/*.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) into `_site/docs/*.html`, rewriting links between them;
   - writes `sitemap.xml` and `robots.txt`, plus structured data (JSON-LD) for the app and the FAQ;
3. uploads `_site/` and deploys it to GitHub Pages.

There are no secrets involved. The workflow uses GitHub's built-in `GITHUB_TOKEN` with the minimum permissions (`pages: write`, `id-token: write`).

## Preview locally

```bash
.venv/bin/pip install markdown
.venv/bin/python site/build.py                 # builds into _site/
.venv/bin/python -m http.server -d _site 8000  # open http://localhost:8000
```

## Connect a custom domain

1. In your DNS provider, add a `CNAME` record from `www.yourdomain.com` (or a subdomain) to `najathi.github.io`. For an apex domain (`yourdomain.com`), add `A` records to GitHub's Pages IPs (`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`).
2. In the repository, go to **Settings → Pages → Custom domain**, enter the domain, save, and tick **Enforce HTTPS** once the certificate is issued.
3. In **Settings → Secrets and variables → Actions → Variables**, add a variable `SITE_URL` with your full URL (for example `https://www.yourdomain.com/`). The next deploy uses it for canonical links, the sitemap and social previews.
4. Update `WEBSITE` in `airdrop_compress/__init__.py`, so the app's links point to the new address.

## Security headers

GitHub Pages serves everything over HTTPS but doesn't allow custom HTTP headers. The site therefore sets what it can in HTML:

- a `Content-Security-Policy` meta tag (only its own scripts, styles and images);
- `referrer` policy `strict-origin-when-cross-origin`;
- no third-party scripts, fonts, trackers or cookies.

`site/_headers` contains the complete header set (CSP, HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`). It's ready if you move to a host that supports header files, such as Cloudflare Pages or Netlify; GitHub Pages ignores it.

## Updating content

- **Landing page:** edit `site/index.html` and `site/assets/`.
- **Docs:** edit the Markdown in `docs/`. Add new pages to `PAGES` in `site/build.py`.
- **Screenshots:** `site/tools/screenshots.py` captures the real app with generated demo files (see the comment at its top). Commit the WebP files it writes to `site/assets/img/`.
