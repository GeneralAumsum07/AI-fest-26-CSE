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

# Cap on media items read per audit (Task 12). None until Task 7's speed
# measurement says how many images fit in the time a person will wait.
MAX_ITEMS: int | None = None

# Leak check (Task 13): secrets shorter than this are not searched for, because
# the payload type has no field that could carry them, and a 3-character
# search would fire on ordinary tokens.
MIN_LEAK_LEN = 4

# Recipes (Task 10).
SEVERAL_FACE_POSTS = 3
AWAY_WINDOW_DAYS = 7
