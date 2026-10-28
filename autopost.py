#!/usr/bin/env python3
"""Publish the next post from queue.json to Instagram (@zeroknownbugs) via the Graph API.

usage:
  python3 autopost.py --list        show the latest posts on the account and which queue items are already out
  python3 autopost.py --dry-run     prepare the next item on Instagram's side (upload + processing) but do NOT publish
  python3 autopost.py               publish the next unpublished item (at most one per run)

Needs IG_USER_ID in the environment. The access token is added to every request to graph.facebook.com
by the environment (network secret), so this script never sees or prints it.
Stateless: an item counts as published when a post on the account starts with the item's first caption line,
so re-running never posts the same item twice. Nothing is published if a queue item went out in the last 18 hours.
Media URLs: MEDIA_BASES (first that Instagram accepts wins).
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.facebook.com/v21.0"
HERE = Path(__file__).resolve().parent
REPO = os.environ.get("MEDIA_REPO", "MLDTS/zeroknownbugs-media")
MEDIA_BASES = [f"https://cdn.jsdelivr.net/gh/{REPO}@main/", f"https://raw.githubusercontent.com/{REPO}/main/"]
MIN_GAP_H = 18


def call(method, path, **params):
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if method == "GET" and params else "")
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"API error {e.code} on {method} {path}: {body[:500]}")


def first_line(text):
    return text.strip().split("\n")[0].strip()


def recent_media(uid):
    out, after = [], None
    for _ in range(4):
        p = {"fields": "id,caption,timestamp,media_type,permalink", "limit": 50}
        if after:
            p["after"] = after
        r = call("GET", f"{uid}/media", **p)
        out += r.get("data", [])
        after = r.get("paging", {}).get("cursors", {}).get("after")
        if not after or "next" not in r.get("paging", {}):
            break
    return out


def status(item):
    """(published_ids, hours since the newest queue post)"""
    uid = os.environ["IG_USER_ID"]
    media = recent_media(uid)
    done, newest = {}, None
    for m in media:
        cap = (m.get("caption") or "").strip()
        for it in QUEUE:
            if cap.startswith(first_line(it["caption"])):
                done.setdefault(it["id"], m)
                t = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
                newest = t if newest is None or t > newest else newest
    gap = None if newest is None else (datetime.now(timezone.utc) - newest).total_seconds() / 3600
    return media, done, gap


def wait_ready(cid, what, limit=600):
    t0 = time.time()
    while True:
        r = call("GET", cid, fields="status_code,status")
        code = r.get("status_code")
        if code == "FINISHED":
            return True
        if code in ("ERROR", "EXPIRED"):
            print(f"  {what}: {code} {r.get('status', '')}")
            return False
        if time.time() - t0 > limit:
            print(f"  {what}: still {code} after {limit}s")
            return False
        time.sleep(10)


def container(uid, item, base):
    files, kind = item["files"], item["type"]
    if kind == "reel":
        cid = call("POST", f"{uid}/media", media_type="REELS", video_url=base + files[0], caption=item["caption"],
                   share_to_feed="true", thumb_offset="1500")["id"]
        return cid if wait_ready(cid, "reel") else None
    if kind == "image":
        cid = call("POST", f"{uid}/media", image_url=base + files[0], caption=item["caption"])["id"]
        return cid if wait_ready(cid, "image") else None
    kids = []
    for f in files:
        k = call("POST", f"{uid}/media", image_url=base + f, is_carousel_item="true")["id"]
        if not wait_ready(k, f):
            return None
        kids.append(k)
    cid = call("POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(kids), caption=item["caption"])["id"]
    return cid if wait_ready(cid, "carousel") else None


def main():
    args = set(sys.argv[1:])
    uid = os.environ.get("IG_USER_ID") or sys.exit("IG_USER_ID is not set")
    acc = call("GET", uid, fields="username,media_count")
    print(f"account @{acc['username']} · {acc['media_count']} posts")
    media, done, gap = status(None)
    todo = [it for it in QUEUE if it["id"] not in done and not it.get("skip")]
    if "--list" in args:
        print("\nlatest posts:")
        for m in media[:25]:
            print(f"  {m['timestamp'][:16]} {m['media_type']:<14} {first_line(m.get('caption') or '')[:80]}")
        print(f"\nqueue: {len(done)} published, {len(todo)} to go")
        for it in QUEUE:
            mark = "✓" if it["id"] in done else ("skip" if it.get("skip") else "·")
            print(f"  {mark:>4} {it['id']:<28} {first_line(it['caption'])[:60]}")
        return
    if not todo:
        print("queue is empty — nothing to post")
        return
    if gap is not None and gap < MIN_GAP_H and "--force" not in args:
        print(f"last queue post was {gap:.1f} h ago (< {MIN_GAP_H} h) — not posting now")
        return
    lim = call("GET", f"{uid}/content_publishing_limit", fields="quota_usage,config").get("data", [{}])[0]
    print(f"publishing quota used: {lim.get('quota_usage')} / {lim.get('config', {}).get('quota_total')}")
    item = todo[0]
    print(f"next: {item['id']} ({item['type']}, {len(item['files'])} file(s))\n  {first_line(item['caption'])}")
    for base in MEDIA_BASES:
        print(f"  media from {base}")
        cid = container(uid, item, base)
        if cid:
            break
    else:
        sys.exit("Instagram could not load the media from any host")
    if "--dry-run" in args:
        print(f"DRY RUN OK — container {cid} is ready; nothing was published")
        return
    post = call("POST", f"{uid}/media_publish", creation_id=cid)["id"]
    link = call("GET", post, fields="permalink").get("permalink")
    print(f"PUBLISHED {item['id']} → {link}")
    print(f"{len(todo) - 1} items left in the queue")


QUEUE = json.loads((HERE / "queue.json").read_text())

if __name__ == "__main__":
    main()
