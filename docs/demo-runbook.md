# Demo runbook

About five minutes. Everything shown is synthetic. Say out loud which beats are live and which were pre-computed.

## Before going on stage

1. Wi-Fi **off**. The report must still render: wording falls back to the offline templates.
2. Start Ollama, then warm the vision model once so the first live image does not pay the load time. Ollama unloads an idle model after about 5 minutes, so do this right before beat 4, not at setup:

   ```bash
   ollama run qwen3.5:4b "ready?"
   ```

3. **Start one server that pre-computes all three personas.** There is only ever one server: a second `python -m selfaudit` would fight it for port 8765. Each `--export` opens its own tab once the server is up. The runs queue on the GPU and finish one after another.

   ```bash
   uv run --offline python -m selfaudit --enrol data/personas/enrol.wav --export data/personas/high.zip --export data/personas/fixed.zip --export data/personas/careful.zip
   ```

   Tab 1 is high, tab 2 is fixed, tab 3 is careful (the fallback for beat 4). Wait until all three show a report. Do not press "Forget this run".
4. Open a fourth tab at `http://127.0.0.1:8765/` and leave it on the start page for the live beat.
5. Have the slide deck open on slide 1.

> TBD (Rachit): `data/personas/*.zip` and `enrol.wav` do not exist yet. They are built in Task 15 step 6 from your own reels, a mock ID post, a birthday caption and a recent travel post.

## The six beats

| # | Beat | Time | Live or pre-computed | What to do |
|---|---|---|---|---|
| 1 | The hook | 30 s | slide | Slide 1: what an attacker's tools can read from a public profile, and why catching the fake at call time fails. |
| 2 | Persona 1, high exposure | 90 s | **pre-computed** (tab 1) | Show the phone-call scam and ID misuse at High. Click "See the posts" on each. Click "This is wrong" on one finding to show the levels update without a reload. |
| 3 | Fix and re-run | 60 s | **pre-computed** (tab 2) | Switch to the fixed export: the top three fixes applied. R3 is gone, R1 is no longer High. "This is the attack path being broken." |
| 4 | Persona 2, the genuine case | 60 s | **live** (tab 4) | Pick `data/personas/careful.zip` on the start page and press "Check my export". It is short, so the wait stays under a minute. It shows no risk and one honest "Not sure". |
| 5 | "What left this laptop?" | 30 s | live, on persona 1's tab | Open the payload. Point out: categories and counts, no name, no caption, no number. "Nothing was sent", because Wi-Fi is off. |
| 6 | Numbers | 45 s | slide | Slide 3: catches, false alarms, rules-only next to the full system, one example it got wrong. |

Do beat 5 before pressing "This is wrong" in beat 2 if you want the payload to match the untouched report. Feedback changes the payload too, which is also worth saying out loud.

## If something breaks

- **GPU or Ollama fails during beat 4:** say so, switch to tab 3, where the careful persona was pre-computed, and carry on. Never pretend a pre-computed run is live.
- **The page does not load:** the server prints its address on start (`http://127.0.0.1:8765/`). It only ever listens on loopback.
- **A run stalls:** the progress view shows the stage and count. Over two minutes means it is stuck: use the pre-computed tab.

## Rehearsal log

Rehearse twice with Wi-Fi off, timed. Target: under five minutes.

| Date | Wi-Fi | Total time | What went wrong |
|---|---|---|---|
| TBD | off | TBD | TBD |
| TBD | off | TBD | TBD |
