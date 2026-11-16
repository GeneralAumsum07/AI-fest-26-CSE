# Final push: four features before midnight — design spec

AI-FEST 2026, CSE Stream. Written 2026-11-16 at 18:32 IST. Deadline: midnight tonight.

**Status:** draft for Rachit's approval. Nothing in here is built.

**Labels.** **[E]** = read in a source this session (the track guide, the repo, a results file). **[C]** = my call, yours to overturn. **[TBD]** = not established, with the question that settles it.

---

## 1. What this is for

The app already meets every item on the track guide's submission checklist **[E: guide p.9, checked against the repo]**. So the question is not "what is missing" but "where would a judge still mark us down, and what can be closed in about three hours of building".

I re-read the track guide against the app as it stands. Four gaps came out of that:

| # | Gap | Where the guide says it | Criterion |
|---|---|---|---|
| G1 | **Prevention is shown with a prepared second file, not in the product.** The demo switches to `fixed.zip` to show levels dropping. A judge sees two reports, not an attack path being broken. | "How well it detects, prevents or responds to the threat" (p.5) | Effectiveness 25% |
| G2 | **The app only looks backwards.** It audits what is already posted. The next risky photo gets posted anyway. Also, the only way to try the app is a whole export, which takes minutes. | "Prevention and awareness" (p.4); "a clear live demo" (p.9) | Innovation 20%, Usability 15% |
| G3 | **"We never open your messages" is a claim on a slide.** The code enforces it and tests prove it, but the user never sees it. | "Show what data you keep (ideally nothing), and how misuse is blocked" (p.4) | Privacy 15% |
| G4 | **The next step for an exposed ID is vague, and nothing reaches the family.** The advice says "watch for loans or SIM cards". The people who get the scam call are the parents, and the safety card is the same for everyone. | "Imagine your parents using it: plain language, obvious next steps" (p.5); the guide names Sanchar Saathi and 1930 (p.8) | Usability 15% |

**Proposed goal, for you to confirm or change:** close G1–G4 with features that reuse the existing pipeline, add no new model and no new dependency, and are frozen by 22:00 so the last two hours go to the deck, a rehearsal and the submission.

**My pushback, stated once.** With five and a half hours left, a rehearsed demo of what exists is worth more than a fifth feature. The guide says so twice ("depth beats breadth", "a focused application that works outscores an ambitious one that half works") **[E: p.2, p.10]**. This spec is four features with a hard cut order. I recommend against adding to it.

---

## 2. Non-goals and anti-goals

**Not doing tonight**

- No new model, no new Python or JS dependency. Every install at this hour is a risk to the demo.
- No change to detection, prompts, thresholds or rules. See the anti-goal below.
- No new platform reader.
- No cloud wording. `make_call_llm()` returns `None` today **[E: wording/cloud.py]**, so the report is always worded offline and the page says "Nothing was sent". That is a simpler and stronger claim than a redacted payload. Keep it, and make sure the deck says the same (section 9).

**Anti-goals (unchanged from the first spec, restated because two new features touch them)**

- **No tuning on the held-out set.** The held-out run shows 6 of 43 benign items flagged, 4 of them confirmed **[E: results/heldout/results.md]**. Those numbers stay as they are. The failing items have been looked at for the slide, so any detection change made now and re-scored on that set would be tuning on test data. If you want fewer false alarms, that is a post-hackathon job with a new test set.
- **No compiled fact sheet about a person, and no attack text.** Feature B must not accumulate results across photos. Feature D must not write what a scammer would say.
- **Never "you are safe".**

---

## 3. Approaches considered

I listed fifteen candidates and scored each on: which criterion it moves, build time, new risk to the demo, and whether its claim could be measured or shown honestly tonight.

**Chosen (sections 4–7)**

| | Feature | Closes | Build estimate **[C]** |
|---|---|---|---|
| A | **Try a fix**: tick a fix in the report and watch the risk levels change | G1 | 50 min |
| B | **Check before you post**: one photo or video in, advice on that item only | G2 | 80 min |
| C | **Privacy receipt**: "opened 14 of 2,310 files; never opened: messages…" | G3 | 35 min |
| D | **Real next steps and a family card that fits the audit** | G4 | 30 min |

Total about 3 h 15 min, which is the whole budget. The cut order is in section 10.

**Considered and dropped**

| Idea | Why not tonight |
|---|---|
| Speech-to-text on reels ("you *said* your mother's name") | The best technical addition on the list, and it was stretch item 3 in the first spec. It needs a new model and a new library on an RTX 50-series card, and there is no labelled audio to measure it on. Unmeasured and able to break the install: no. |
| Report in Hindi and Telugu | The offline templates are English-only on purpose: "untested hand translations of risk advice are worse than English" **[E: wording/templates.py]**. A local 4B model writing Telugu for Telugu-speaking judges, unreviewed, is a bigger risk than English. A reduced version is in section 7 as an optional extra, gated on a human reader. |
| Lower the false-alarm numbers | Anti-goal: tuning on test data (section 2). |
| Auto-blur the ID number and hand back a safe copy | Needs reliable bounding boxes from the vision model. Not tested, and a blur that misses one digit is worse than no blur. |
| More recipes (account recovery, fake job offers) | Breadth. The guide marks that down. |
| AI-written scam drill for the family | It would mean generating persuasion text. Anti-goal, and the guide's FAQ forbids making attacks easier **[E: p.9]**. |
| "Attacker's view" dossier screen | A compiled fact sheet. Anti-goal. |
| LinkedIn / Reddit reader | Breadth, and a new unverified layout. YouTube's layout is already unverified. |
| Wire a hosted LLM for wording | Adds a network dependency and an API key to a demo that currently runs with Wi-Fi off, for nicer sentences. |
| Exposure timeline chart, risk history, PDF export | No criterion moves. |
| YouTube held-out evaluation | Worth doing, but building and labelling a second frozen set is hours. Stay with the current honest caveat. |

---

## 4. Feature A — Try a fix

### What the user sees

In "Recommended actions", every fix gets a tick box labelled **"Try this"**. Ticking one or more:

- The risk cards above update in place. A card whose level changed shows both: `High → Low`. A recipe that would disappear stays on screen, greyed, labelled **"No longer possible with these changes"**, so the user sees what they broke.
- A banner appears at the top of the report: **"Preview. This shows your report after the changes you ticked. Nothing has been changed on Instagram. You still need to make these changes yourself."** (On YouTube, "on YouTube".) A **"Clear preview"** button unticks everything.
- Unticking restores the real report.

```
┌ Preview. This shows your report after the changes you ticked. ──────┐
│ Nothing has been changed on Instagram.            [Clear preview]   │
└─────────────────────────────────────────────────────────────────────┘
  A phone call to your family in your voice        High → Low
  Misuse of your ID document       No longer possible with these changes
  A copy of your profile                           Low

  Recommended actions
  [x] Try this   1. Delete post 3 (ends: misuse of your ID document)
  [ ] Try this   2. Archive post 7 (lowers: a phone call to your family…)
```

### How it works

- New endpoint `POST /api/audits/{id}/preview` with body `{"fixes": [0, 2]}`: indexes into the **current** report's `fixes` list.
- The server computes the report fresh (as it always does), applies the chosen fixes to a **copy** of the findings and voice result using the existing `fixes._apply`, and evaluates the recipes on the copy. `AuditState` is never changed: a preview is not feedback.
- Response: `{"recipes": [...after...], "text": {...}}` in the same shape the report endpoint uses for those two keys, so the page reuses its card renderer. The fix list on screen does not change while previewing; only the cards do.
- An index outside the list is a 422.
- "This is wrong" / "Add a finding" while a preview is showing: clear the preview first, then apply the feedback, because the fix list is recomputed and the old indexes no longer mean anything.

### Why this and not a re-run

The first spec's "before and after" needed a second, hand-edited export. This is the same computation the fix ranker already runs internally to decide the order **[E: fixes.rank_fixes]**, shown to the user. It answers "what happens if I do this" in under a second, and in the demo it replaces the switch to `fixed.zip`.

### The number that goes on the slide

A small script (`devtools/`, run once, output to `results/`) that, for each of the personas, records recipe levels before, after the top one fix, and after the top three. This is a count over four synthetic personas, reported as counts, labelled as a demonstration and not as proof. **[TBD: the numbers. They do not exist until the script runs. Nothing goes on the slide before then.]**

### Tests

- Preview with one fix returns the same recipe levels as `rank_fixes`' own `after` for that fix.
- Preview does not change the next `GET /report` (state untouched).
- Empty list returns the real report's recipes. Bad index is 422. Unfinished run is 409.
- Nothing extracted is served by the new endpoint (reuse the existing secrets check).

---

## 5. Feature B — Check before you post

### What the user sees

A second entry on the start page, under the export picker: **"About to post something? Check one photo or video first."** The user picks one file and can paste the caption they plan to use. About six seconds later (see "Speed" below) they get one of three results:

| Result | Heading | When |
|---|---|---|
| Stop | **"Wait before you post this."** | At least one confirmed finding in a category that matters on its own: a readable ID number, a card or account number, a ticket or boarding pass, a phone number or email. |
| Look | **"Have a look at this first."** | Likely or unsure findings, or a confirmed one that only matters in combination (a family member named, "away" wording, a college name). |
| Nothing | **"Nothing urgent was identified in this photo."** followed by "This does not mean it is safe to post. The check looks for ID and bank details, tickets, contact details, family names and travel plans." | No findings. |

Under the heading: one line per finding in the words the report already uses ("an Aadhaar-format number"), and one line of advice per category ("Cover or crop the number, then check again"). Never the value itself. A **"Check another"** button clears the screen.

**Which categories count as "Stop" versus "Look" is a product decision with no single right answer.** A college name on a lanyard is normal; a boarding pass is not. The table above is my proposal. This rule is about ten lines in one function and is a good piece for you to write yourself (section 11).

### How it works

- New endpoint `POST /api/check` taking one file (`image/*` or `video/*`) and an optional `caption` form field. Size cap 50 MB **[C]**; over the cap is a plain message.
- It builds the same `ItemInput` objects the audit builds (one for an image; keyframes for a video, caption on the first frame) and calls the same `analyse_items` with all readers, so vision, the rules layer, the caption reader and grounding all run exactly as in an audit. For a video, the per-video merge added today applies, so one ID seen in five frames is one line.
- It shares the audit's GPU lock: a check waits for a running audit, and the page says "An audit is running. Your check will start when it finishes."
- **No voice step.** Voice is a profile-level measure (total seconds across all reels); a single clip cannot say anything useful about it. The result says so for videos: "Speech in this video was not measured. The full audit does that."
- **No recipes, no roll-up, no fixes, no memory.** Each check stands alone. Nothing links one check to the next or to an audit. This is the misuse rule from the first spec (section 11, "single-post mode"), kept exactly.
- The file is held in memory for the request and dropped. Nothing is written to disk. The response carries categories, the "what" phrase and the confidence, never `value` (same exclusion as the report).

### Speed, and one thing that must be measured before the demo

The audit unloads the vision model when it finishes, to free the GPU for the voice model **[E: perceive/items.py]**. A check that runs after an audit would pay the model's load time. **[C]** For checks, skip the unload so the model stays warm between checks; Ollama drops it after its idle timeout anyway. The audit's own unload is unchanged.

Measured speed today is 588 s for 100 items, about 6 s per item, with the model warm **[E: deck notes, dev run]**. **[TBD: the cold-start time for the first check. Measure it once the endpoint exists. If it is over about 20 s, the runbook must warm the model before the beat.]**

### What can honestly be claimed about its accuracy

The held-out test is scored per item: one photo plus its caption **[E: first spec section 10]**. A check runs the same code path on one photo plus its caption. So the held-out numbers (40 of 40 risky flagged; 6 of 43 benign flagged) describe this feature too, **provided the check uses the full reader set and the same grounding**. That is a requirement, and it gets a test. The Stop / Look / Nothing split is a new presentation layer on top and has **not** been evaluated; the slide must not imply it has.

### Misuse

| Misuse | What stops or limits it |
|---|---|
| Feeding it scraped photos of someone else to find the "good" ones | It answers about one item, shows no extracted values, keeps nothing and builds no list. It is slower and less informative than looking at the photo. This limits the harm; it does not prevent the attempt. Say so. |
| Using it to tune a forged document until it passes | It does not judge whether a document is genuine. It only says "a number is readable here". |

### Tests

- An image with a mock ID (scripted backends) returns the Stop result and no value.
- A benign image returns the Nothing result, and its text never contains "safe to post" without "not".
- The check and an audit of the same item produce the same findings (same code path).
- Two checks in a row share nothing: the second response has no trace of the first.
- Non-image upload, oversize upload, unreadable image: a plain message each, no stack trace.

---

## 6. Feature C — Privacy receipt

### What the user sees

A panel in the report, next to "Data transparency":

```
What was opened
  Files in your export          2,310
  Opened for this audit            14
  Never opened                  2,296
    Messages                    1,204
    Ads and businesses            310
    Search and browsing history    88
    Everything else               694
  Kept after you close this page    0
```

One sentence under it: "The audit opens the profile file, the lists of your posts, and the photos and videos those lists name. It cannot open anything else."

### How it works

- The export reader already records every file it opens in `ExportSource.opened` **[E: ingest/export.py]**. At the end of the read, count the ZIP's entries, subtract the opened ones, and group the rest by top-level folder through a **fixed table** of folder name to plain label. Anything not in the table is "Everything else".
- Only counts and fixed labels leave the reader. Never a file name: message folders are named after the people in them.
- The counts ride on `Profile` and then `Report` as a small `access` object: `{total, opened, never_opened: [{label, count}]}`.
- Media the page later serves as thumbnails comes from the same allowlist, so "opened" in the receipt means "opened to build the report".
- YouTube exports get their own label table (watch history, comments, live chat, subscriptions).

### The demo needs a decoy

The receipt only lands if the persona ZIP contains folders the audit refuses. **[TBD: do `data/personas/*.zip` contain a `messages/` folder and other non-allowlisted folders? I could not list them this session. If not, the persona builder adds synthetic decoy files (empty JSON, placeholder names) and the personas are rebuilt.]** Decoys are synthetic like everything else; the runbook says so.

### Tests

- A ZIP with `messages/inbox/chat.json` and an ads folder: `opened` excludes them, the counts add up to the total, and the labels are from the fixed table.
- No file or folder name from the ZIP appears in the served report (extend the existing "nothing extracted is served" test with a decoy folder named after a person).
- A folder with an unknown name is counted under "Everything else".

---

## 7. Feature D — Real next steps, and a family card that fits the audit

### D1. Next steps when an ID or bank detail is exposed

Today the advice for "Misuse of your ID document" ends with "watch for loans or SIM cards you did not ask for" **[E: wording/templates.py]**. Replace "watch for" with things a person can do tonight. Proposed steps **[C]**, each to be **checked against the official page before it ships**, because the guide says to check these sources directly **[E: p.8]** and I have not verified any of them this session:

1. Check which mobile numbers are registered in your name on the Sanchar Saathi portal. **[TBD: confirm the current name and address of this service.]**
2. Lock your Aadhaar biometrics from the UIDAI site or app. **[TBD: confirm this exists in this form and what it is called.]**
3. If you see a loan, SIM or account you did not open: call 1930 or report at cybercrime.gov.in. (Already on the safety card **[E: index.html]**.)

**Any step that cannot be confirmed on the official site in ten minutes is dropped, not reworded.** Wrong official advice is worse than short advice. The steps are shown only when the document recipe is shown, as a short numbered list under its advice. They are fixed text: no personal detail, no cloud call.

### D2. A family card that says what a caller might know

The printed safety card is the same for everyone today **[E: index.html]**. Add one block, built from the audit's categories:

> **A caller might know these things. That does not make the call real.**
> - A family member's name
> - Where they study or work
> - That they are travelling right now
> - What their voice sounds like

Each line appears only if the audit found that ingredient. This is the link from "before" to "during": parents trust a caller who knows correct details, and the card tells them in advance that the details are public. It names categories only, never the values, so a printed card that is lost gives nothing away. If the audit found none of these, the block is not printed.

It describes what a caller could know. It does not describe what a caller would say. That line keeps it out of attack-text territory.

### D3. Optional, only with a human reader: the card in Hindi and Telugu

Only the fixed card text (four rules plus the D2 lines, about a dozen short sentences), chosen by a language picker on the card. **Gate:** a person fluent in the language reads every line before it ships. **[TBD: can you, or a teammate, review Hindi? Telugu? If nobody can review a language tonight, that language is not built.]** The report itself stays in English.

### Tests

- D1: the steps appear with the document recipe and not without it.
- D2: each line appears only with its ingredient; no extracted value appears on the card; no ingredients, no block.

---

## 8. Constraints that apply to all four

- **Same privacy rules as the rest of the app.** Loopback only. Nothing written to disk. No value served. Every new endpoint goes through the existing "nothing extracted is served" test.
- **Wording rules.** No percentages or scores. Never "safe". Platform words follow the platform ("video" on YouTube), using the helper added today.
- **Comments explain why**, as everywhere in this repo.
- **Each feature is one commit**, with its tests, and the full suite green (211 tests today **[E]**) before the next one starts. A feature that is not green at its cut time is reverted, not left half in.
- **`app.js` version bump.** Any change to `app.js` bumps the `?v=` in `index.html`, or browsers show the old page. This cost twenty minutes today.

---

## 9. Deck and demo changes

These are part of the work, not an afterthought. The deck has to match what is shown.

**Demo script (replaces beats 3–5 of the runbook)**

| # | Beat | Time | What happens |
|---|---|---|---|
| 1 | Hook | 30 s | Slide. Unchanged. |
| 2 | High-exposure persona | 75 s | Pre-computed report. Two risks at High. |
| 3 | **Try a fix** (A) | 40 s | Tick the top fix. "Misuse of your ID document" becomes "No longer possible". Tick the next. The phone-call risk drops. One tab, no second file. |
| 4 | **Check before you post** (B) | 60 s | Live. A restaurant bill: "Nothing urgent was identified". Then a specimen ID: "Wait before you post this". This is the genuine case and an attack case, live, in about fifteen seconds. Pre-computed careful persona stays open in another tab as the fallback. |
| 5 | **Privacy receipt** (C) | 30 s | "Opened 14 of 2,310 files. Messages: never opened." Then the payload view: "Nothing was sent." |
| 6 | **Family card** (D2) | 20 s | Print preview. "A caller might know these things." |
| 7 | Numbers | 45 s | Slide. Unchanged, plus the before/after counts from A if they exist. |

Total five minutes. **[TBD: is there a time limit for the demo, and what do the submission guidelines ask for? The guide says they are "shared separately" [E: p.2]. Have they arrived, and is midnight the time the form closes?]**

**Deck**

- The "How it works" or "Using it" slide gains the two new things a user can do (try a fix, check before posting). No new slide: the guide asks for 4–5 and the deck has 10 already.
- The results slide gains the before/after persona counts, if the script has produced them.
- The privacy slide's "Sent" row must say what is true tonight: nothing is sent; the wording is done on the laptop. **[TBD: I have not re-read the deck's privacy slide against this. Check it when the deck is rebuilt.]**
- The "Next" slide keeps LinkedIn and the "see what a stranger sees" idea, and gains "speech-to-text on reels" and "report in Hindi and Telugu" as honest next steps.
- Limits slide: add "the Stop / Look / Nothing wording on single-photo checks has not been evaluated separately".

---

## 10. Order, clock and cut lines

Times are IST. The order is by value per minute and by what the demo most needs **[C]**.

| When | Work | Cut rule |
|---|---|---|
| now – 19:35 | **A. Try a fix** + the persona before/after script | Never cut. It replaces a weak demo beat. |
| 19:35 – 20:55 | **B. Check before you post** | If the endpoint is not returning a correct result by 20:30, drop the video path and ship images only. |
| 20:55 – 21:30 | **C. Privacy receipt** (and persona decoys if needed) | If personas need rebuilding and that is not done by 21:20, show the receipt on whatever the personas hold and say what it would show on a real export. |
| 21:30 – 22:00 | **D1 and D2** | D1 only with confirmed official pages. D3 only if a reviewer is on hand and everything else is green. |
| **22:00** | **Code freeze.** Full suite, one live audit, one live check. | Anything not green is reverted. |
| 22:00 – 23:00 | Deck rebuild, runbook rewrite, measured numbers onto slides | |
| 23:00 – 23:35 | Two timed rehearsals, Wi-Fi off | |
| 23:35 | Commit, push, submit | 25 minutes of buffer. |

If you want fewer features so there is more rehearsal time, drop from the bottom: D first, then C.

---

## 11. Left to the builder

- Layout and styling of the three new UI pieces, inside the existing design.
- How the preview marks a changed card (the wording above is fixed; the visual treatment is not).
- The folder-to-label table for the receipt, read off the real folder names in an export.
- Whether the check keeps the model warm by skipping the unload or by an explicit keep-alive.
- **For you to write, if you want it:** the Stop / Look / Nothing rule in feature B. One function: findings in, one of three results out. It decides how often a user gets told to stop, which is the difference between a tool people listen to and one they ignore.

---

## 12. Questions for you

Each has a default the build will use if you do not answer.

| # | Question | Default |
|---|---|---|
| 1 | Is the goal in section 1 the right one, or do you want something riskier and bigger? | As written |
| 2 | All four features, or fewer with more rehearsal? | All four, with the cut lines |
| 3 | Submission guidelines: what must be handed in, and does the form close at midnight? | Assume repo link + deck, due 23:59 |
| 4 | Do you want to write the Stop / Look / Nothing rule yourself? | I write the proposal in section 5 and you review it |
| 5 | Can anyone review Hindi or Telugu card text tonight? | No, so D3 is not built |
| 6 | Are you the one presenting, alone? (Affects how much rehearsal the new beats need.) | Yes |

---

## 13. Sources

- Track guide: `AI-FEST-2026_CSE-Stream_Track-Guide.pdf`, all ten pages, re-read this session.
- First design spec: `docs/superpowers/specs/2026-11-14-exposure-self-audit-design.md` (outer project folder).
- Held-out results: `results/heldout/results.md`. Voice: `results/voice_test.json`.
- Code read: `fixes.py`, `app.py`, `pipeline.py`, `ingest/export.py`, `perceive/items.py`, `wording/templates.py`, `wording/cloud.py`, `static/index.html`, `static/app.js`, `deck/build.js`, `docs/demo-runbook.md`.
- Not verified this session: every official-portal step in D1; the contents of the persona ZIPs; the deck's privacy slide wording; the submission guidelines.
