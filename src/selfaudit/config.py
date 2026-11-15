"""Every tunable value in one place.

Why one file: the held-out set may only be used once, after tuning is finished,
so every threshold has to be tuned on the development split and then frozen.
Keeping them together makes it obvious what was tuned and makes the final
values easy to show on a slide. Later tasks append to this file.
"""

# Ollama listens on loopback only; the vision model never sees the network.
OLLAMA_HOST = "http://127.0.0.1:11434"

# First choice from spec section 8. Task 0's hour-0 check decides the final tag;
# if it fails, move down the fallback list and do not redesign anything.
VISION_MODEL = "qwen3.5:4b"
VISION_FALLBACKS = ["qwen3-vl:4b", "qwen2.5vl:7b", "qwen3.5:2b"]
# Qwen3-family models "think" before answering by default, which costs seconds
# per image and adds nothing to a schema-constrained listing. None means "do
# not send the flag" (for models that reject it).
VISION_THINK: bool | None = False
# Hard bounds on every model call. Clipping the parsed answer happens after the
# model has finished; these stop a looping model or a hung server from holding
# the GPU lock for the whole audit. Provisional and unmeasured: a normal answer
# (a few findings and a short transcription) is estimated well under 2048
# tokens. An answer cut off at the cap fails to parse and takes the existing
# short-prompt retry. Retune both on the development split once the model is in.
MODEL_MAX_TOKENS = 2048
MODEL_TIMEOUT_S = 120.0

# Presidio's phone recogniser scores 0.4 before context words, so anything
# higher would drop bare phone numbers (Task 3).
SCORE_THRESHOLD = 0.4

# Video keyframes (Task 8): one frame every 3 s, at most 8 per video. Eight
# frames keeps a 60 s reel to the cost of eight photos on the vision model.
KEYFRAME_EVERY_S = 3.0
KEYFRAME_MAX = 8

# Voice (Task 9). SIM_THRESHOLD is the cosine score at which a segment counts as
# the enrolled speaker; 0.25 is believed to be SpeechBrain's verification default
# (from memory, not checked) and is tuned on half of the audio set.
SIM_THRESHOLD = 0.25
# Speaker embeddings from scraps under a second are unreliable, so skip them.
MIN_SEGMENT_S = 1.0
# DefaultGate: a segment is "clean" when its speech is at least this many dB
# above the clip's own non-speech parts (music, crowd, wind). Tuned in Task 9.
CLEAN_SNR_DB = 15.0

# Cap on media items read per audit (Task 12), newest first; the rest are
# listed as "couldn't check (over limit)", never silently dropped.
# Measured 2026-11-16 (100 dev items, warm RTX 5060, qwen3.5:4b): a photo
# costs ~4 s end to end (2.9 s image + 1.1 s caption), a long reel ~30 s
# (8 frames + caption + 6.4 s voice). Target wait: about 5 minutes. 40 items
# is ~2.7 min all photos, ~4 min for a ~10% reel mix, leaving room for the
# 83 s cold model load measured at hour 0. Not a hard bound: the cap counts
# files, not frames, so a profile of only long reels still runs ~20 min.
MAX_ITEMS: int | None = 40

# Leak check (Task 13): secrets shorter than this are not searched for, because
# the payload type has no field that could carry them, and a 3-character
# search would fire on ordinary tokens.
MIN_LEAK_LEN = 4

# Recipes (Task 10).
SEVERAL_FACE_POSTS = 3
AWAY_WINDOW_DAYS = 7
