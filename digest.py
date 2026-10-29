#!/usr/bin/env python3
"""Daily engagement shortlist for @zeroknownbugs: fresh posts from QA accounts, for the owner to like and comment on by hand.

usage:
  python3 digest.py [N]          N fresh posts (default 8) from the accounts in accounts.json, as JSON
  python3 digest.py --discover   check the seed accounts + accounts they @mention; print who is usable

Read-only: only GET requests (Business Discovery = public posts of business/creator accounts).
Nothing is liked, commented or posted. The token is added by the environment; this script never sees it.
"""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.facebook.com/v21.0"
HERE = Path(__file__).resolve().parent
SEEDS = ["softwaretestingandautomation", "testify_org", "qacetech", "codoid.innovations", "spurqlabs", "qaontop",
         "luxequality_", "jignect", "astaqcconsulting", "qualitician"]
QA_WORDS = ("test", "qa", "quality", "bug", "automation", "selenium", "playwright", "sdet", "cypress", "api", "developer")
SKIP_WORDS = ("giveaway", "follow for follow", "f4f", "crypto", "betting", "casino", "onlyfans")


def get(path, **params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace")[:300]}


def account(uid, name, limit=12):
    f = (f"business_discovery.username({name}){{username,name,biography,followers_count,media_count,"
         f"media.limit({limit}){{caption,permalink,timestamp,like_count,comments_count,media_type}}}}")
    r = get(uid, fields=f)
    return r.get("business_discovery") if "error" not in r else {"error": r["error"]}


def age_h(ts, now):
    return (now - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")).total_seconds() / 3600


def discover(uid):
    now, seen, rows, queue = datetime.now(timezone.utc), set(), [], list(SEEDS)
    while queue and len(seen) < 60:
        name = queue.pop(0).lower().strip(".")
        if name in seen or name == "zeroknownbugs":
            continue
        seen.add(name)
        a = account(uid, name)
        if not a or "error" in a:
            rows.append({"username": name, "ok": False, "why": (a or {}).get("error", "not found")[:120]})
            continue
        media = a.get("media", {}).get("data", [])
        caps = " ".join((m.get("caption") or "") for m in media)
        if name in SEEDS:  # one level of snowball: accounts the seeds mention
            queue += [m for m in re.findall(r"@([A-Za-z0-9_.]{3,30})", caps)]
        last = min((age_h(m["timestamp"], now) for m in media), default=9999)
        qa = sum(w in (a.get("biography", "") + caps).lower() for w in QA_WORDS)
        rows.append({"username": name, "ok": True, "followers": a.get("followers_count"), "posts": a.get("media_count"),
                     "last_post_days": round(last / 24, 1), "qa_score": qa, "bio": (a.get("biography") or "")[:100]})
    good = [r for r in rows if r.get("ok") and r["qa_score"] >= 3 and r["last_post_days"] <= 30
            and 500 <= (r["followers"] or 0) <= 200000]
    print(json.dumps({"usable": good, "checked": len(rows), "all": rows}, ensure_ascii=False, indent=1))


def shortlist(uid, n):
    names = json.loads((HERE / "accounts.json").read_text())
    now, posts, errors = datetime.now(timezone.utc), [], []
    for name in names:
        a = account(uid, name, 6)
        if not a or "error" in a:
            errors.append(f"@{name}: {(a or {}).get('error', 'not found')[:150]}")
            continue
        for m in a.get("media", {}).get("data", []):
            cap = (m.get("caption") or "").strip()
            h = age_h(m["timestamp"], now)
            if h > 96 or len(cap) < 30 or any(w in cap.lower() for w in SKIP_WORDS):
                continue
            posts.append({"account": name, "permalink": m.get("permalink"), "type": m.get("media_type"), "age_hours": round(h),
                          "likes": m.get("like_count"), "comments": m.get("comments_count"), "caption": cap[:600]})
    posts.sort(key=lambda p: p["age_hours"])
    picked, per = [], {}
    for p in posts:  # at most one post per account, freshest first
        if not per.get(p["account"]):
            picked.append(p); per[p["account"]] = 1
        if len(picked) == n:
            break
    print(json.dumps({"posts": picked, "candidates": len(posts), "errors": errors}, ensure_ascii=False, indent=1))


def main():
    uid = os.environ.get("IG_USER_ID") or sys.exit("IG_USER_ID is not set")
    if "--discover" in sys.argv:
        return discover(uid)
    shortlist(uid, int(next((a for a in sys.argv[1:] if a.isdigit()), 8)))


if __name__ == "__main__":
    main()
