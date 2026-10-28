# zeroknownbugs-media

Public images and videos for the **@zeroknownbugs** Instagram account, plus the script that publishes them.
No paid study notes (PDF) live here.

- `queue.json` — posts in publishing order (type, media files, caption)
- `media/` — reels (mp4), carousel slides and pinned posts (jpg)
- `autopost.py` — publishes the next unpublished item (one per run); `--list` shows status, `--dry-run` prepares without publishing

Generated from `branding/make_ig_queue.py` in the private MLDTS/QA repo.
