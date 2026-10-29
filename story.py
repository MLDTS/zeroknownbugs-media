#!/usr/bin/env python3
"""Publish today's story (one QA meme a day) to @zeroknownbugs.

usage: python3 story.py [--dry-run]
Item for today = days since stories.json "start" (Kyiv date). Nothing is posted if a story already went out
in the last 20 hours, before the start date, or after the last item. --dry-run prepares the container only.
The token is added by the environment (network secret); this script never sees or prints it.
"""
import json, sys, time, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from autopost import call, MEDIA_BASES, wait_ready

HERE = Path(__file__).resolve().parent
KYIV = timezone(timedelta(hours=2))  # close enough for picking the day (EET; EEST shifts it by an hour)


def main():
    dry = "--dry-run" in sys.argv
    uid = os.environ.get("IG_USER_ID") or sys.exit("IG_USER_ID is not set")
    cfg = json.loads((HERE / "stories.json").read_text())
    day = (datetime.now(KYIV).date() - datetime.strptime(cfg["start"], "%Y-%m-%d").date()).days
    if day < 0 or day >= len(cfg["items"]):
        print(f"no story for today (day {day} of {len(cfg['items'])}) — nothing to post")
        return
    live = call("GET", f"{uid}/stories", fields="id,timestamp").get("data", [])
    now = datetime.now(timezone.utc)
    recent = [s for s in live if (now - datetime.strptime(s["timestamp"], "%Y-%m-%dT%H:%M:%S%z")).total_seconds() < 20 * 3600]
    if recent and not dry:
        print(f"a story was already posted in the last 20 h ({len(recent)} live) — not posting now")
        return
    item = cfg["items"][day]
    print(f"today: day {day + 1}/{len(cfg['items'])} · {item['id']}")
    for base in MEDIA_BASES:
        cid = call("POST", f"{uid}/media", media_type="STORIES", image_url=base + item["file"])["id"]
        if wait_ready(cid, "story"):
            break
    else:
        sys.exit("Instagram could not load the story image from any host")
    if dry:
        print(f"DRY RUN OK — story container {cid} is ready; nothing was published")
        return
    sid = call("POST", f"{uid}/media_publish", creation_id=cid)["id"]
    print(f"PUBLISHED story {item['id']} (id {sid})")


if __name__ == "__main__":
    main()
