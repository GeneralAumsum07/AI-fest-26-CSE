"""Synthetic LinkedIn and Reddit exports, for tests and the demo.

Both platforms export flat folders of CSV files with no photos or videos, so
a persona here is just a few tables. The headers are the ones the reader is
written against:

- Reddit: from Reddit's help page "What is in my Reddit data copy" (file
  names) and a published parser of the export (posts.csv columns: id,
  permalink, date, ip, subreddit, gildings, title, url, body). comments.csv
  columns are an assumption built the same way (UNCONFIRMED).
- LinkedIn: file names from published parsers of "Get a copy of your data"
  (Profile.csv, Positions.csv, Education.csv). The Shares.csv headers are
  UNCONFIRMED; the reader matches columns by keyword so a renamed header
  still reads.

The extra files (messages, connections, votes, ip logs) exist so the privacy
receipt has something to show as "never opened". Their contents are
placeholders: the reader must refuse them whatever they hold.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

LINKEDIN_PROFILE = ["First Name", "Last Name", "Maiden Name", "Address", "Birth Date", "Headline", "Summary",
                    "Industry", "Zip Code", "Geo Location", "Twitter Handles", "Websites", "Instant Messengers"]
LINKEDIN_POSITIONS = ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"]
LINKEDIN_EDUCATION = ["School Name", "Start Date", "End Date", "Notes", "Degree Name", "Activities"]
LINKEDIN_SHARES = ["Date", "ShareLink", "ShareCommentary", "SharedUrl", "MediaUrl", "Visibility"]
# Never read by the app; present only so the receipt can count them.
LINKEDIN_PRIVATE = {"messages.csv": ["FROM", "TO", "DATE", "SUBJECT", "CONTENT"],
                    "Connections.csv": ["First Name", "Last Name", "Email Address", "Company"],
                    "Email Addresses.csv": ["Email Address", "Confirmed", "Primary"],
                    "PhoneNumbers.csv": ["Extension", "Number", "Type"]}

REDDIT_POSTS = ["id", "permalink", "date", "ip", "subreddit", "gildings", "title", "url", "body"]
REDDIT_COMMENTS = ["id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"]
REDDIT_PRIVATE = {"messages.csv": ["id", "permalink", "thread_id", "date", "ip", "from", "to", "subject", "body"],
                  "chat_history.csv": ["message_id", "created_at", "username", "message", "channel_name"],
                  "ip_logs.csv": ["date", "ip"],
                  "post_votes.csv": ["id", "permalink", "direction"],
                  "saved_posts.csv": ["id", "permalink"],
                  "subscribed_subreddits.csv": ["subreddit"]}


def _csv(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({h: r.get(h, "") for h in headers})
    return buf.getvalue().encode("utf-8")


def _write(files: dict[str, bytes], out: Path, as_zip: bool, wrapper: str) -> Path:
    prefix = f"{wrapper}/" if wrapper else ""
    if as_zip:
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w") as z:
            for name, data in files.items():
                z.writestr(prefix + name, data)
        return out
    for name, data in files.items():
        p = out / prefix / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return out


def build_linkedin_export(out: Path, *, profile: dict[str, str], positions: list[dict[str, str]] = (),
                          education: list[dict[str, str]] = (), shares: list[dict[str, str]] = (),
                          as_zip: bool = False, wrapper: str = "", private_rows: int = 3) -> Path:
    files = {"Profile.csv": _csv(LINKEDIN_PROFILE, [profile]),
             "Positions.csv": _csv(LINKEDIN_POSITIONS, list(positions)),
             "Education.csv": _csv(LINKEDIN_EDUCATION, list(education)),
             "Shares.csv": _csv(LINKEDIN_SHARES, list(shares))}
    for name, headers in LINKEDIN_PRIVATE.items():
        # Placeholder rows that would leak if ever read (a test checks they are not).
        files[name] = _csv(headers, [{h: f"PRIVATE-{name}-{i}" for h in headers} for i in range(private_rows)])
    return _write(files, out, as_zip, wrapper)


def build_demo(out_dir: Path) -> tuple[Path, Path]:
    """The demo's LinkedIn and Reddit ZIPs: one synthetic student, exposed the
    way the Instagram persona is (family, away, college, contact, an ID number).

        uv run python -m selfaudit.devtools.text_persona data/personas
    """
    import random

    from selfaudit.devtools.synthetic import valid_aadhaar

    n = valid_aadhaar(random.Random(11))   # checksum-valid, issued to nobody: synthetic
    aadhaar = f"{n[:4]} {n[4:8]} {n[8:]}"
    li = build_linkedin_export(
        out_dir / "linkedin.zip", as_zip=True, wrapper="Basic_LinkedInDataExport_11-16-2026",
        profile={"First Name": "Asha", "Last Name": "Verma", "Address": "Flat 4B, Kondapur",
                 "Birth Date": "Mar 3, 2005", "Headline": "B.Tech CSE student at Mahindra University, Hyderabad",
                 "Summary": "Open to internships. Call or WhatsApp me on 98765 43210."},
        positions=[{"Company Name": "Infosys", "Title": "Summer Intern", "Started On": "May 2026"}],
        education=[{"School Name": "Mahindra University", "Degree Name": "B.Tech Computer Science"}],
        shares=[
            {"Date": "2026-11-14 19:00:00", "ShareCommentary": "Flying to Singapore tomorrow for a two-week "
             "exchange programme! Back on the 30th.", "Visibility": "PUBLIC"},
            {"Date": "2026-11-02 10:00:00", "ShareCommentary": "Amma and Appa came all the way from Vizag for "
             "my hackathon finals. Thank you Amma!", "MediaUrl": "https://media.licdn.com/dms/image/demo",
             "Visibility": "MEMBER_NETWORK"},
            {"Date": "2026-09-20 09:00:00", "ShareCommentary": "Excited to start my final year.",
             "Visibility": "PUBLIC"},
        ])
    rd = build_reddit_export(
        out_dir / "reddit.zip", as_zip=True,
        posts=[
            {"id": "d1", "date": "2026-11-12 22:10:00 UTC", "ip": "198.51.100.23", "subreddit": "hyderabad",
             "title": "Lost my Aadhaar card near Kondapur bus stop",
             "body": f"Number on it is {aadhaar}. Please DM if anyone finds it.", "url": ""},
            {"id": "d2", "date": "2026-10-28 18:00:00 UTC", "ip": "198.51.100.23", "subreddit": "Indian_Academia",
             "title": "Mahindra University CSE workload is insane", "body": "Third year here, any tips?", "url": ""},
            {"id": "d3", "date": "2026-10-10 12:00:00 UTC", "ip": "198.51.100.23", "subreddit": "IndianFood",
             "title": "Made biryani in the hostel", "body": "", "url": "https://i.redd.it/demo1234.jpg"},
        ],
        comments=[
            {"id": "e1", "date": "2026-11-15 08:30:00 UTC", "ip": "198.51.100.23", "subreddit": "india",
             "body": "My Amma got one of those 'your son is arrested' calls last week. Scary stuff."},
            {"id": "e2", "date": "2026-11-01 08:30:00 UTC", "ip": "198.51.100.23", "subreddit": "travel",
             "body": "Going to Singapore mid-November, any tips for Changi?"},
        ])
    return li, rd


def build_reddit_export(out: Path, *, posts: list[dict[str, str]] = (), comments: list[dict[str, str]] = (),
                        as_zip: bool = False, wrapper: str = "", private_rows: int = 3) -> Path:
    files = {"posts.csv": _csv(REDDIT_POSTS, list(posts)),
             "comments.csv": _csv(REDDIT_COMMENTS, list(comments))}
    for name, headers in REDDIT_PRIVATE.items():
        files[name] = _csv(headers, [{h: f"PRIVATE-{name}-{i}" for h in headers} for i in range(private_rows)])
    return _write(files, out, as_zip, wrapper)


if __name__ == "__main__":
    import sys

    for p in build_demo(Path(sys.argv[1] if len(sys.argv) > 1 else "data/personas")):
        print(p)
