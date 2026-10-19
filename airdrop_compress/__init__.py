"""AirDrop Compress - turns files received via AirDrop into web-ready images and Markdown."""

import time as _time

# Files that arrive while the app is still starting up (slow imports) must count as new.
PROCESS_STARTED = _time.time()

__version__ = "2.1.0"

APP_NAME = "AirDrop Compress"
BUNDLE_ID = "com.najathi.airdropcompress"
GITHUB_REPO = "najathi/airdrop-compress"

# Shown in the app's "Built by" / business inquiry card and on the website.
AUTHOR = "Najathi"
CONTACT_EMAIL = "najathi777@gmail.com"
WEBSITE = "https://najathi.github.io/airdrop-compress/"
AUTHOR_LINKS = {
    "GitHub": "https://github.com/najathi",
    "LinkedIn": "https://www.linkedin.com/in/najathi/",
    "Stack Overflow": "https://stackoverflow.com/users/9181204/najathi",
}
