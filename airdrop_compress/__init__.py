"""AirDrop Compress - turns files received via AirDrop into web-ready images and Markdown."""

import time as _time

# Files that arrive while the app is still starting up (slow imports) must count as new.
PROCESS_STARTED = _time.time()

__version__ = "2.0.0"

APP_NAME = "AirDrop Compress"
BUNDLE_ID = "com.najathi.airdropcompress"
GITHUB_REPO = "najathi/airdrop-compress"
