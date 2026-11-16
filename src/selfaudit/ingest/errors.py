"""The one error every export reader raises.

Its own module so the Instagram reader (export.py) and the YouTube reader
(youtube.py) can both raise it without importing each other.
"""


class NotAnExport(Exception):
    """Raised with a short reason the app turns into a plain message.

    html_export:   the user picked HTML instead of JSON when requesting the export.
    multi_part:    most referenced media is absent; the export came in several ZIPs.
    missing_files: this does not look like a supported export at all.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
