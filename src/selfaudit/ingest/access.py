"""The privacy receipt: how much of the export the audit opened, in counts only.

ExportSource records every file it opens (export.py). Here the listing is
compared with that record, and the never-opened files are grouped under a
FIXED table of plain labels. Only counts and those labels leave this module:
never a file or folder name, because Instagram names message folders after
the people in them ("inbox/priyasharma_123456/").

A count, not a promise: "opened" is what this run's reader opened, which is
the profile file, the post lists and the media those lists name.
"""

from __future__ import annotations

from selfaudit.models import Access, AccessGroup

# Path segment -> label. A file is labelled by the first segment of its path
# that appears here, so "your_instagram_activity/messages/..." and an older
# export's top-level "messages/..." are both "Messages". Instagram and YouTube
# folder names do not collide, so one table serves both. Order of insertion
# is the display order.
LABELS: dict[str, str] = {
    # Instagram
    "messages": "Messages",
    "ads_information": "Ads and businesses",
    "ads_and_businesses": "Ads and businesses",
    "logged_information": "Search and watch history",
    "recent_searches": "Search and watch history",
    "connections": "Followers and contacts",
    "followers_and_following": "Followers and contacts",
    # YouTube (Google Takeout)
    "history": "Search and watch history",
    "comments": "Comments",
    "live chats": "Live chat",
    "subscriptions": "Subscriptions",
}
# LinkedIn and Reddit export flat folders of CSVs, so there the label comes
# from a root-level file name. Only exact names from this fixed table: the
# platform sets those names, never a person, so a label still cannot carry
# anyone's name.
ROOT_FILES: dict[str, str] = {
    # LinkedIn
    "messages.csv": "Messages",
    "Connections.csv": "Followers and contacts",
    "Email Addresses.csv": "Email and phone on the account",
    "PhoneNumbers.csv": "Email and phone on the account",
    "Comments.csv": "Comments",
    "SearchQueries.csv": "Search and watch history",
    "Ad_Targeting.csv": "Ads and businesses",
    # Reddit
    "chat_history.csv": "Messages",
    "message_headers.csv": "Messages",
    "friends.csv": "Followers and contacts",
    "linked_phone_number.csv": "Email and phone on the account",
    "ip_logs.csv": "Sign-in and IP logs",
    "post_votes.csv": "Votes, saves and subscriptions",
    "comment_votes.csv": "Votes, saves and subscriptions",
    "poll_votes.csv": "Votes, saves and subscriptions",
    "saved_posts.csv": "Votes, saves and subscriptions",
    "saved_comments.csv": "Votes, saves and subscriptions",
    "hidden_posts.csv": "Votes, saves and subscriptions",
    "subscribed_subreddits.csv": "Votes, saves and subscriptions",
}
EVERYTHING_ELSE = "Everything else"
_ORDER = list(dict.fromkeys([*LABELS.values(), *ROOT_FILES.values()])) + [EVERYTHING_ELSE]


def _label(name: str) -> str:
    if "/" not in name and name in ROOT_FILES:
        return ROOT_FILES[name]
    for seg in name.split("/")[:-1]:          # folders only; a file name is never matched
        if seg.lower() in LABELS:
            return LABELS[seg.lower()]
    return EVERYTHING_ELSE


def summarise(names: set[str], opened: set[str]) -> Access:
    """Counts of the listing, what was opened, and the rest by fixed label."""
    opened_here = opened & names              # never count a name that is not in the export
    counts: dict[str, int] = {}
    for n in names - opened_here:
        lbl = _label(n)
        counts[lbl] = counts.get(lbl, 0) + 1
    return Access(total=len(names), opened=len(opened_here),
                  never_opened=[AccessGroup(label=l, count=counts[l]) for l in _ORDER if counts.get(l)])
