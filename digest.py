#!/usr/bin/env python3
"""Daily engagement shortlist for @zeroknownbugs: fresh QA posts by hashtag, for the owner to like and comment on by hand.

usage: python3 digest.py [N]      -> prints N posts (default 8) as JSON: permalink, caption, likes, comments, age
Read-only: only GET requests (hashtag search + public media). Nothing is liked, commented or posted.
The access token is added by the environment (network secret); this script never sees or prints it.
Instagram allows 30 unique hashtags per 7 days, so the list below stays short and fixed.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

API = "https://graph.facebook.com/v21.0"
TAGS = ["softwaretesting", "qatester", "qaengineer", "testautomation", "playwright", "qualityassurance", "sdet"]
SKIP_WORDS = ("giveaway", "follow for follow", "f4f", "dm for", "crypto", "betting", "casino", "onlyfans")
FIELDS = "id,caption,permalink,media_type,timestamp,like_count,comments_count"


def get(path, **params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace")[:400]}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    uid = os.environ.get("IG_USER_ID") or sys.exit("IG_USER_ID is not set")
    now, seen, posts, errors = datetime.now(timezone.utc), set(), [], []
    for tag in TAGS:
        h = get("ig_hashtag_search", user_id=uid, q=tag)
        if "error" in h or not h.get("data"):
            errors.append(f"#{tag}: {h.get('error', 'not found')}")
            continue
        hid = h["data"][0]["id"]
        for edge in ("recent_media", "top_media"):
            r = get(f"{hid}/{edge}", user_id=uid, fields=FIELDS, limit=30)
            if "error" in r:
                errors.append(f"#{tag}/{edge}: {r['error']}")
                continue
            for m in r.get("data", []):
                cap = (m.get("caption") or "").strip()
                if m["id"] in seen or len(cap) < 40 or any(w in cap.lower() for w in SKIP_WORDS):
                    continue
                age_h = (now - datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")).total_seconds() / 3600
                if age_h > 72:
                    continue
                seen.add(m["id"])
                posts.append({"tag": tag, "permalink": m.get("permalink"), "type": m.get("media_type"),
                              "age_hours": round(age_h), "likes": m.get("like_count"), "comments": m.get("comments_count"),
                              "caption": cap[:600]})
    # favour posts where a comment is still visible: some traction, not buried under hundreds of comments
    posts.sort(key=lambda p: (-(min(p["likes"] or 0, 300)) + (p["comments"] or 0) * 2, p["age_hours"]))
    picked, per_tag = [], {}
    for p in posts:
        if per_tag.get(p["tag"], 0) < 2:
            picked.append(p); per_tag[p["tag"]] = per_tag.get(p["tag"], 0) + 1
        if len(picked) == n:
            break
    print(json.dumps({"posts": picked, "candidates": len(posts), "errors": errors}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
