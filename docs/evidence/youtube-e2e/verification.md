# YouTube end-to-end verification

Run on 16 November 2026 using a separate loopback server on port 8766.
The existing app on port 8765 was left running. No commits or pushes were made.

The browser uploaded a newly generated synthetic Takeout ZIP and a separate
synthetic enrolment recording. All inference used the production backends:
Qwen3.5 4B through Ollama, GLiNER, Presidio, Silero VAD and SpeechBrain ECAPA.
No model responses were simulated. No held-out images or audio were used.

## Passed

- Two public videos audited; two videos marked private/unlisted excluded.
- Reader opened only channel/video metadata and allowed public media, excluding
  history, comments, subscriptions and the hidden media.
- Actual MP4 keyframes and AAC speech decoded and analysed.
- Found ID_DOCUMENT, CONTACT, FAMILY_RELATION and AWAY_STATUS on the risky video.
- Neutral public video produced no asserted finding.
- Counted 10.6 seconds of matching speech, moderate band, enrolment enabled.
- Rendered report, risk levels, ranked fix and public thumbnails in the browser.
- Hidden-video thumbnail requests returned 404.
- Extracted synthetic ID/contact values and excluded-content sentinels did not
  appear in the report JSON or wording payload. Offline wording was used.
- Browser "This is wrong" removed the contact finding and recomputed R1 from
  High to Medium without rerunning models.
- Payload panel opened and remained redacted.
- "Forget this run" returned 204; the old report then returned 404 and the
  browser returned to the upload page.
- Default suite after the display fix: 203 passed, 2 GPU tests deselected.

## Fix made

Added the missing browser label for `not_public`. It now says the video was
marked private or unlisted and excluded from the audit. Verified the original
failure and the corrected rendering against the same completed audit.

## Limits and remaining issue

- The Takeout folder layout and CSV headers remain guesses. This is a real
  production-pipeline test on a synthetic archive, not proof that a real Google
  Takeout archive is compatible.
- Visibility that is missing or unknown is audited, as disclosed on the page.
- Repeated keyframes of the same document can show duplicate ID findings in
  the report. No deduplication or model thresholds were changed in this run.
- There was one harmless browser console error for the absent favicon.

Evidence: `fixture-summary.json`, `summary.json`, `report.json`, `payload.json`,
and `report.png` in this directory. All fixtures and evidence remain git-ignored.

## Later update

Added when this record was copied into the repository; the run above is
unchanged. The duplicate ID findings from repeated keyframes were fixed
afterwards in commit c8da02b: findings from one video now collapse to one per
category, keeping the strongest frame. This browser run was not repeated after
that fix; the fix is covered by unit tests only.

Only this file and `summary.json` are in the repository. The other evidence
files named above (fixtures, report JSON and screenshots) stay out of git.
