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
