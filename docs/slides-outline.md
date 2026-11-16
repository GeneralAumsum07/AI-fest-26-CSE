# Slide content (five slides, spec section 13)

The original source for the deck. The built deck (`deck/build.js`, 11 slides) has grown past these five; section 5b below is the slide added for the final-push features.

The source for the deck. Build the deck from this once slide 3's numbers exist (Task 15 step 5).
Every `TBD` needs a measured number or a re-checked source. Nothing here is invented to fill a gap.

---

## 1. The threat, and why we act before it (Innovation 20%)

**Headline:** Scammers build the call to your parents out of your own posts.

| | |
|---|---|
| Attacker | A scammer doing open-source reconnaissance on one person. No hacking, no account access. |
| Target | College students with a public Instagram. The people who pay are their family. |
| Goal | Money: "Mum, I've had an accident, send money", or misuse of an ID document. |
| Method | Voice from reels, face photos, family names from captions, "I'm away" posts, ID numbers in photos. |
| Our defence | Show the student which ingredients their profile supplies, which scams those are enough for, and the smallest set of changes that breaks them. |
| Stage | **Before** (exposure). |

Why not catch the fake on the call: voice-clone detectors drop to 59.6% on replayed audio (EchoFake). People spot deepfakes about 55.5% of the time.

Scale, both **TBD: re-verify against primary sources before use** (Task 16 step 4). Drop either one that can't be confirmed.
- ₹19,813 crore lost, 21.77 lakh complaints on the national portal in 2025. This is secondary reporting; find the I4C/MHA release.
- McAfee 2026 voice-clone survey figure. Vendor survey, URL not captured; re-find it or drop it.

## 2. How it works (Technical aptitude 25%)

Pipeline: export ZIP → allowlisted reader → keyframes + audio → vision model (all images) → caption reader → unload → rules layer (Presidio + checksums + lexicon) → grounding → ingredients → recipes R1–R3 → ranked fixes → redacted wording.

One line per model:
- **Qwen3.5 4B via Ollama**: reads documents and scenes on an 8 GB laptop GPU; one model loaded at a time.
- **GLiNER PII**: names in captions, small and on the CPU.
- **Silero VAD + SpeechBrain ECAPA**: finds speech, then checks it is *your* voice against one spoken sentence.
- **Presidio + Verhoeff/Luhn checksums**: a number only counts as an ID if the checksum passes. This is where the rules are, because a 4B model misreads digits.

Recipes are data, not model output: three recipes, ten level rules in one function. Fixes are ranked greedily: each pick is the one that ends or weakens the most recipes.

## 3. Does it work (Effectiveness 25%)

**TBD: every number here comes from the single held-out run** (`results/results.md`). Counts first, then percentages with 95% intervals.

| System | Risky flagged | Benign flagged (confirmed) |
|---|---|---|
| B0 rules only | TBD | TBD |
| B1 vision only | TBD | TBD |
| B2 text only | TBD | TBD |
| Full | TBD | TBD |
| 15 real photographs (own row) | TBD | TBD |

- Before and after: high persona R1 TBD / R3 TBD → fixed persona R1 TBD / R3 TBD.
- Voice: band correct TBD of TBD test clips; other-speaker seconds counted TBD.
- One miss and one false alarm, shown as images: TBD.

## 4. Privacy and misuse (Privacy 15%)

| | |
|---|---|
| Read | Profile info, posts/stories/reels indexes, the media they reference |
| Never opened | Messages, contacts, searches, ad data; on LinkedIn the account email and phone; on Reddit votes, saves and IP logs (posts are read without their IP column) |
| Kept | Nothing. Temp folder wiped on exit; the voice clip stays in memory |
| Sent | Only the redacted payload, only if online wording is on, viewable in the app. The server listens on loopback only |

Misuse: needs the owner's own export (no username or scraping path); outputs fixes, not a fact sheet; no scam scripts, no voice cloning.
**Unsolved:** someone could hand-build a fake export from scraped photos. This raises their effort; it does not stop them.

## 5. Using it, limits, credits (Usability 15%)

- Report screenshot: TBD (take it from the high persona). Show one "Not sure" card.
- Limits, from spec 15:
  - Exposures found, not scams prevented.
  - Synthetic test data and a small set with wide intervals.
  - Voice thresholds are heuristics.
  - A 4B model misreads digits.
  - Four platforms: Instagram and YouTube (photos, video, voice); LinkedIn and Reddit (text only, since their exports hold no photos). LinkedIn and Reddit are tested on synthetic exports only, and some of their column names are unconfirmed.
  - The export format can change.
- Credits:
  - Models: Qwen3.5 (Alibaba, Apache-2.0), GLiNER PII (Apache-2.0), SpeechBrain ECAPA (Apache-2.0), Silero VAD.
  - Libraries: Presidio, spaCy, FastAPI, PyTorch, PyAV, Ollama.
  - Format facts: the Timelinize importer (AGPL; facts only, no code).
  - Prior art: Visual Privacy Advisor (2017), PrivAR (2026), consumer footprint checkers, Thamba and Satark (the "during" stage).
  - An AI coding assistant was used for planning and coding.

## 5b. Before, during and after posting (Usability 15%)

Deck slide 9, kicker "05  USING IT". Added 16 November 2026 for the features in `docs/superpowers/specs/2026-11-16-final-push-design.md`. One measured number per tile; caveats live in the speaker notes.

| Tile | Number on the slide | What it says |
|---|---|---|
| Try a fix | High → None | Ticking the top fix ends ID misuse on the high-risk profile; two fixes take the phone-call scam from Medium to Low. A preview: nothing changes on Instagram. |
| Check before you post | Stop · Look · Nothing | One photo or video checked before posting. Mock Aadhaar: Stop, 7.6 s warm. Food photo: Nothing, 0.5 s. "Nothing" never says safe. |
| What was opened | 13 of 98 files | A receipt in counts; the 85 never-opened files include 60 message files. Fixed labels, never a folder name. |
| Next steps and the family card | 3 checked steps | Sanchar Saathi, UIDAI biometric lock, 1930, each checked on the official site. The card lists what a caller might know: categories, never values. |

Speaker-note caveats:
- Single timed runs on synthetic personas, not benchmarks. A cold first check took 18 s.
- Stop / Look / Nothing is a hand-written rule and has not been evaluated. A boarding pass read as "likely" gives Look.
- The 85 never-opened files are synthetic placeholders; the reader refuses them, and a test checks that.
- Next steps were checked on sancharsaathi.gov.in and uidai.gov.in on 16 November 2026; fixed text, never reworded online.
