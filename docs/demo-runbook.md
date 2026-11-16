# Demo runbook

About 5 min 15 s, all eight beats kept. Everything shown is synthetic. Say out loud which beats are live and which were pre-computed.

## Before going on stage

1. Wi-Fi **off**. The report must still render: wording falls back to the offline templates.
2. **Start one server that pre-computes the personas.** There is only ever one server: a second `python -m selfaudit` would fight it for port 8765. Each `--export` (a folder or a ZIP) opens its own tab once the server is up. The runs queue on the GPU and finish one after another.

   ```bash
   uv run --offline python -m selfaudit --export data/personas/high/instagram-asha.synthetic --export data/personas/fixed/instagram-asha.synthetic.fixed --export data/personas/careful/instagram-meera.synthetic
   ```

   Tab 1 is high, tab 2 is fixed, tab 3 is careful (the fallback for beat 5). Wait until all three show a report. Do not press "Forget this run".

   For the optional LinkedIn and Reddit beat (5b), add two more exports to the same command. They are text only, so each runs in under 30 s (26 s and 8 s live on 16 November):

   ```bash
   --export data/personas/reddit.zip --export data/personas/linkedin.zip
   ```

   Tab 4 is then Reddit and tab 5 LinkedIn, and the start page in step 3 becomes the sixth tab. Build the two ZIPs first if `data/personas` does not have them: `uv run python -m selfaudit.devtools.text_persona data/personas`.

   There is no voice reference (`enrol.wav`) for the demo personas, so the report shows the "Add a voice reference" line. Speech is still measured.
3. Open another tab at `http://127.0.0.1:8765/` and leave it on the start page for the live beats.
4. **Warm the vision model right before beat 4**, not at setup. Ollama unloads an idle model after about 5 minutes. A cold first check took 18 s on 16 November; warm checks took 0.5 to 8 s.

   ```bash
   ollama run qwen3.5:4b "ready?"
   ```

5. `data/personas/careful.zip` (for beat 5) was built on 16 November from the careful folder and checked with a live upload. Rebuild it if the folder changes.
6. Have the slide deck open on slide 1. Keep `data/personas/_media/aadhaar.jpg` and `c_food.jpg` easy to find for beat 4.

## The beats

| # | Beat | Time | Live or pre-computed | What to do |
|---|---|---|---|---|
| 1 | The hook | 30 s | slide | Slide 1: what an attacker's tools can read from a public profile, and why catching the fake at call time fails. |
| 2 | Persona 1, high exposure | 75 s | **pre-computed** (tab 1) | Show the phone-call scam and ID misuse at High. Under ID misuse, point at the three numbered steps (Sanchar Saathi, UIDAI biometric lock, 1930). Click "See the posts" on one card. |
| 3 | Try a fix | 45 s | **live**, on tab 1 | Tick "Try this" on the top fix: ID misuse goes High → None. Tick the second: the phone-call scam goes Medium → Low. Say: "This is a preview. Nothing on Instagram changed." Optionally switch to tab 2 (the fixed export) to show the same levels from a real re-run. Press "Clear preview". |
| 4 | Check before you post | 45 s | **live** (start-page tab) | Check `aadhaar.jpg`: "Wait before you post this." Then `c_food.jpg`: "Nothing urgent", with the line that this does not mean safe. |
| 5 | Persona 2, the genuine case | 45 s | **live** (start-page tab) | Pick `data/personas/careful.zip` on the start page and run it. It shows no risk and one honest "Not sure". If the GPU stalls, use tab 3. |
| 5b | *Optional:* LinkedIn and Reddit | 20 s | **pre-computed** (tabs 4 and 5) | Reddit tab: the Aadhaar number in a "lost my card" post gives ID misuse at Medium, and the receipt says 2 files opened, messages, IP logs and votes never. LinkedIn tab: the fix for the phone number says "Take the detail out of your profile", not a post number. Say: "Text only: these exports hold no photos." |
| 6 | "What left this laptop?" | 30 s | live, on tab 1 | Show "What was opened" (13 of 98 files; 85 never opened, 60 of them messages), then the payload: categories and counts, no name, no caption, no number. "Nothing was sent", because Wi-Fi is off. |
| 7 | The family card | 15 s | tab 1 | Scroll to the card: "A caller might know these things. That does not make the call real." Categories only. |
| 8 | Numbers | 30 s | slide | Results slide: catches, false alarms, rules-only next to the full system, one example it got wrong. |

The beats total about 5 min 15 s on paper. All eight stay in (decided 16 November); no beat is cut for time. Beat 5b is extra: with it the demo runs about 5 min 35 s, so drop it first if the clock is tight.

Do beat 6 before pressing "This is wrong" anywhere if you want the payload to match the untouched report. Feedback changes the payload too, which is also worth saying out loud.

## What to say if asked

- **The 85 never-opened files are synthetic placeholders** added to the demo exports so the receipt has something to show. The reader refuses them, and a test checks that.
- **Stop / Look / Nothing is a hand-written rule**: Stop for a confirmed ID, bank, travel document or contact detail; Look for anything else found; Nothing otherwise. It has not been evaluated. A boarding pass the model reads as "likely" gives Look, not Stop.
- **LinkedIn and Reddit are text only.** Their exports list a post's photo as a link, so the report names it under "couldn't check" and the app never goes online to fetch it. Both were tested on synthetic exports; some column names in a real export are unconfirmed.
- **Why "your profile" on LinkedIn:** the headline, About section and job history are read as one item. Its fix says edit your profile, and the posts are numbered without it.
- **Reddit has no name in its export,** so the "copy of your profile" scam never claims one there. Comments are numbered with the posts ("post 3" can be a comment).
- **The next steps were checked on the official sites** (sancharsaathi.gov.in, uidai.gov.in) on 16 November 2026. They are fixed text and are never reworded by the online wording.

## If something breaks

- **GPU or Ollama fails during beat 4 or 5:** say so, switch to tab 3, where the careful persona was pre-computed, and carry on. Never pretend a pre-computed run is live.
- **"Check" says "An audit is running":** a queued run is still on the GPU, and the check waits for it. Let tabs 1 to 3 finish before beat 4 so the check starts at once.
- **The page does not load:** the server prints its address on start (`http://127.0.0.1:8765/`). It only ever listens on loopback.
- **A run stalls:** the progress view shows the stage and count. Over two minutes means it is stuck: use the pre-computed tab.

## Rehearsal log

Rehearse twice with Wi-Fi off, timed. Target: about 5 min 15 s, the planned length.

| Date | Wi-Fi | Total time | What went wrong |
|---|---|---|---|
| TBD | off | TBD | TBD |
| TBD | off | TBD | TBD |
