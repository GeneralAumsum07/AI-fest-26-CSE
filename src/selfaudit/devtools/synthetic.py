"""Synthetic labelled data: mock documents, compositing and the dev / held-out sets.

Why synthetic: the track allows only synthetic, public or consented data, and
nobody may photograph a real Aadhaar card for a test set. So every document is
drawn here, carries a visible "SPECIMEN - SYNTHETIC" band, and uses numbers
that are checksum-valid (so the recogniser treats them as real) but invented.

The generator is deterministic for a given (split, seed): the held-out set can
be rebuilt bit-for-bit and checked against its frozen manifest.
"""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Literal

import yaml
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pydantic import BaseModel

from selfaudit.models import Category

SPECIMEN = "SPECIMEN - SYNTHETIC"

MVP_ITEM_CATEGORIES: list[Category] = [
    "ID_DOCUMENT", "FINANCIAL", "TRAVEL_DOC", "CONTACT", "FAMILY_RELATION",
    "AWAY_STATUS", "INSTITUTION", "FACE_CLEAR",
]

DocKind = Literal["aadhaar", "pan", "passport", "debit_card", "boarding_pass", "college_id"]


class ItemLabel(BaseModel):
    item_id: str
    file: str
    caption: str
    categories: list[Category]
    values: dict[str, str]
    hard_negative: bool = False
    real_photo: bool = False


# --- Numbers ---------------------------------------------------------------

# Verhoeff tables: the checksum Aadhaar uses. It catches every single-digit
# error and every adjacent swap, which is why invalid_aadhaar() only needs to
# change one digit to guarantee a failure.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_ok(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def _verhoeff_digit(body: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(body)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def valid_aadhaar(rng: random.Random) -> str:
    """12 digits, first digit 2-9, Verhoeff-valid, not a palindrome.

    These are the same conditions the recogniser checks, so a "valid" number
    here is one the pattern layer will accept, which is what the tests need.
    """
    while True:
        body = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
        n = body + _verhoeff_digit(body)
        if n != n[::-1]:
            return n


def invalid_aadhaar(rng: random.Random) -> str:
    """Same shape as a valid number, but one digit off so the checksum fails."""
    n = valid_aadhaar(rng)
    last = int(n[-1])
    return n[:-1] + str((last + rng.randint(1, 9)) % 10)


def _luhn_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return str((10 - total % 10) % 10)


def _card_number(rng: random.Random) -> str:
    body = "4" + "".join(str(rng.randint(0, 9)) for _ in range(14))
    return body + _luhn_digit(body)


def _pan(rng: random.Random) -> str:
    # Fourth letter P marks an individual's PAN, which is what a student holds.
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    return f"{letters}P{rng.choice(string.ascii_uppercase)}{rng.randint(1000, 9999)}{rng.choice(string.ascii_uppercase)}"


# --- Drawing ---------------------------------------------------------------

_NAMES = ["Asha Rao", "Kiran Reddy", "Meera Iyer", "Rohan Gupta", "Sneha Patil", "Arjun Nair"]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _card(color: tuple[int, int, int], title: str, lines: list[str], big: str,
          rng: random.Random) -> Image.Image:
    """Draw one card. The large `big` line is the number a reader must find;
    its box is stored in image.info so composite() can hide it on request."""
    img = Image.new("RGB", (860, 540), color)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 860, 90], fill=tuple(max(c - 60, 0) for c in color))
    d.text((30, 25), title, fill=(255, 255, 255), font=_font(40))
    # A face placeholder makes documents look like documents to the model.
    d.rectangle([30, 120, 230, 360], fill=(180, 180, 180), outline=(90, 90, 90), width=3)
    y = 130
    for line in lines:
        d.text((260, y), line, fill=(20, 20, 20), font=_font(30))
        y += 48
    box = (260, 400, 820, 460)
    d.text(box[:2], big, fill=(0, 0, 0), font=_font(50))
    # The specimen band crosses the whole card so no crop can remove it.
    band = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.text((80, 230), SPECIMEN, fill=(220, 0, 0, 170), font=_font(64))
    img = Image.alpha_composite(img.convert("RGBA"), band.rotate(rng.uniform(-12, 12))).convert("RGB")
    img.info["number_box"] = box
    return img


def make_document(kind: DocKind, rng: random.Random) -> tuple[Image.Image, dict[str, str]]:
    """Draw a mock document; return it with the values printed on it."""
    name = rng.choice(_NAMES)
    if kind == "aadhaar":
        n = valid_aadhaar(rng)
        img = _card((235, 240, 250), "Government of India (mock)",
                    [name, f"DOB: {rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(2000, 2007)}"],
                    f"{n[:4]} {n[4:8]} {n[8:]}", rng)
    elif kind == "pan":
        n = _pan(rng)
        img = _card((210, 230, 245), "Income Tax Department (mock)", [name, "Permanent Account Number"], n, rng)
    elif kind == "passport":
        n = f"{rng.choice('JKLMNPRSTVWZ')}{rng.randint(1000000, 9999999)}"
        img = _card((40, 60, 120), "Republic of India Passport (mock)", [name, "Nationality: Indian"], n, rng)
    elif kind == "debit_card":
        n = _card_number(rng)
        img = _card((30, 90, 70), "Mock Bank Debit", [name, f"Valid thru {rng.randint(1, 12):02d}/{rng.randint(27, 31)}"],
                    " ".join(n[i:i + 4] for i in range(0, 16, 4)), rng)
    elif kind == "boarding_pass":
        n = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        src, dst = rng.sample(["HYD", "BOM", "DEL", "GOI", "BLR", "MAA"], 2)
        img = _card((250, 250, 245), "BOARDING PASS (mock)",
                    [name, f"{src} -> {dst}  Flight 6E {rng.randint(100, 999)}", f"Seat {rng.randint(1, 30)}{rng.choice('ABCDEF')}"],
                    f"PNR {n}", rng)
    elif kind == "college_id":
        n = f"{rng.randint(20, 25)}B{rng.randint(10, 99)}A{rng.randint(1000, 9999)}"
        img = _card((250, 240, 220), "Mock Institute of Technology", [name, "Student Identity Card"], n, rng)
    else:  # pragma: no cover - Literal guards this
        raise ValueError(kind)
    return img, {"number": n, "name": name, "specimen": SPECIMEN}


def composite(doc: Image.Image, background: Image.Image, rng: random.Random, *,
              occlude_number: bool = False) -> Image.Image:
    """Place a document in a scene the way a phone photo would: tilted, warped,
    slightly blurred, with uneven light. Clean flat renders would overstate
    how well the vision model reads real photos."""
    doc = doc.copy()
    if occlude_number:
        box = doc.info.get("number_box", (0, 0, 0, 0))
        ImageDraw.Draw(doc).rectangle(box, fill=(90, 70, 60))  # a thumb over the number
    bg = background.convert("RGB").resize((1280, 960))
    doc = doc.convert("RGBA").rotate(rng.uniform(-25, 25), expand=True, resample=Image.BICUBIC)
    # Mild perspective: shrink one edge a little, as when a card is held at an angle.
    w, h = doc.size
    dx, dy = rng.uniform(0, 0.08) * w, rng.uniform(0, 0.08) * h
    coeffs = _perspective_coeffs(
        [(0, 0), (w, 0), (w, h), (0, h)],
        [(dx, dy), (w - dx * rng.random(), 0), (w, h - dy * rng.random()), (0, h)],
    )
    doc = doc.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    scale = rng.uniform(0.55, 0.8) * 1280 / w
    doc = doc.resize((int(w * scale), int(h * scale)))
    x = rng.randint(0, max(1280 - doc.width, 0))
    y = rng.randint(0, max(960 - doc.height, 0))
    bg.paste(doc, (x, y), doc)
    bg = bg.filter(ImageFilter.GaussianBlur(rng.uniform(0, 1.2)))
    return ImageEnhance.Brightness(bg).enhance(rng.uniform(0.7, 1.2))


def _perspective_coeffs(src, dst):
    """Solve the 8 coefficients PIL's PERSPECTIVE transform wants (maps dst -> src)."""
    import numpy as np

    rows = []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(rows, dtype=float)
    b = np.array([c for p in src for c in p], dtype=float)
    return np.linalg.solve(a, b).tolist()


def _poster(lines: list[str], rng: random.Random, color=(250, 245, 230)) -> Image.Image:
    """A plain printed thing (bill, ticket, cover, meme): text on a card."""
    img = Image.new("RGB", (800, 1000), color)
    d = ImageDraw.Draw(img)
    # Ink follows the card: dark ink on a dark card (the concert ticket) left
    # an unreadable picture, which tests nothing. Rec. 601 luma decides.
    light = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2] > 128
    ink = (30, 30, 30) if light else (245, 245, 245)
    y = 80
    for line in lines:
        d.text((60, y), line, fill=ink, font=_font(44))
        y += 90
    return img


def _hard_negative(kind: str, rng: random.Random, background: Image.Image) -> tuple[Image.Image, str]:
    """Things that look risky to a careless reader but expose nothing personal (spec 9.2)."""
    if kind == "bill":
        return _poster(["Spice Garden", "Biryani  x2   480.00", "Lassi    x2   120.00",
                        f"Total Rs {rng.randint(500, 900)}.00", "GSTIN 36AAACS1234Z1Z5"], rng), "dinner was great"
    if kind == "ticket":
        return _poster(["LIVE IN CONCERT", "Gate C  Row K", "Admit one", "No refunds"], rng, (30, 30, 60)), "tonight!!"
    if kind == "book":
        return _poster(["THE QUIET RIVER", "a novel", "", "Paperback edition"], rng, (200, 220, 200)), "currently reading"
    if kind == "meme":
        n = invalid_aadhaar(rng)
        return _poster(["me explaining to my mom", f"that {n[:4]} {n[4:8]} {n[8:]}", "is not my roll number"], rng), "lol"
    if kind == "occluded_id":
        doc, _ = make_document("aadhaar", rng)
        return composite(doc, background, rng, occlude_number=True), "new card finally"
    if kind == "helpline":
        return _poster(["Cyber Crime Helpline", "Dial 1930", "Report fraud early"], rng, (255, 240, 200)), "share this"
    if kind == "order":
        n = "1" + "".join(str(rng.randint(0, 9)) for _ in range(11))
        return _poster(["Order confirmed", f"Order no {n}", "Arriving Tuesday"], rng), f"order {n} finally shipped"
    raise ValueError(kind)


_HARD_KINDS = ["bill", "ticket", "book", "meme", "occluded_id", "helpline", "order"]
_DOC_FOR = {"ID_DOCUMENT": ["aadhaar", "pan", "passport"], "FINANCIAL": ["debit_card"],
            "TRAVEL_DOC": ["boarding_pass"]}
# Categories carried by captions rather than pictures.
_CAPTION_CATS = ["CONTACT", "FAMILY_RELATION", "AWAY_STATUS"]


def _photos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))


def generate_set(out_dir: Path, *, split: Literal["dev", "heldout"], seed: int,
                 sources: Path) -> list[ItemLabel]:
    """Write a labelled split to out_dir (images + labels.json) and return its labels.

    Held-out quotas come from spec 9.2: >= 35 risky, >= 25 benign, >= 12 hard
    negatives, >= 4 per MVP category. Dev is a smaller copy (~30 items) with
    the same mix, used for every bit of tuning.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Seeding with the split name as well as the seed keeps dev and held-out
    # number streams apart even if someone reuses a seed by mistake.
    rng = random.Random(f"{split}:{seed}")
    backgrounds = [Image.open(p).convert("RGB") for p in _photos(sources / "backgrounds")]
    faces = _photos(sources / "faces")
    campus = _photos(sources / "institution")
    captions = yaml.safe_load((sources / "captions.yaml").read_text(encoding="utf-8"))
    neutral = [c for c in captions if not c.get("categories") and not c.get("hard_negative")] or [{"text": ""}]
    hard_caps = [c for c in captions if c.get("hard_negative")]

    per_cat, plain_benign, hard_reps = (5, 13, 2) if split == "heldout" else (2, 7, 1)
    labels: list[ItemLabel] = []

    def save(img: Image.Image, caption: str, cats: list[str], values: dict, hard: bool = False):
        item_id = f"{split}-{len(labels):03d}"
        img.convert("RGB").save(out_dir / f"{item_id}.jpg", "JPEG", quality=90)
        labels.append(ItemLabel(item_id=item_id, file=f"{item_id}.jpg", caption=caption,
                                categories=sorted(set(cats)), values=values, hard_negative=hard))

    for cat in MVP_ITEM_CATEGORIES:
        for i in range(per_cat):
            bg = rng.choice(backgrounds)
            cap = rng.choice(neutral)["text"]
            if cat in _DOC_FOR:
                doc, vals = make_document(rng.choice(_DOC_FOR[cat]), rng)
                save(composite(doc, bg, rng), cap, [cat], {"number": vals["number"]})
            elif cat == "INSTITUTION":
                # Alternate a college ID card and a campus photo: both name the institution.
                if i % 2 == 0 or not campus:
                    doc, vals = make_document("college_id", rng)
                    save(composite(doc, bg, rng), cap, [cat], {"number": vals["number"]})
                else:
                    save(Image.open(rng.choice(campus)), cap, [cat], {})
            elif cat == "FACE_CLEAR":
                save(Image.open(rng.choice(faces)), cap, [cat], {})
            else:
                pool = [c for c in captions if cat in (c.get("categories") or [])]
                c = rng.choice(pool)
                save(bg, c["text"], list(c["categories"]), dict(c.get("values") or {}))

    for _ in range(plain_benign):
        save(rng.choice(backgrounds), rng.choice(neutral)["text"], [], {})
    for _ in range(hard_reps):
        for kind in _HARD_KINDS:
            img, cap = _hard_negative(kind, rng, rng.choice(backgrounds))
            save(img, cap, [], {}, hard=True)
        for c in hard_caps:
            save(rng.choice(backgrounds), c["text"], [], {}, hard=True)

    (out_dir / "labels.json").write_text(
        json.dumps([l.model_dump() for l in labels], ensure_ascii=False, indent=1), encoding="utf-8")
    return labels


def load_labels(dir: Path) -> list[ItemLabel]:
    data = json.loads((Path(dir) / "labels.json").read_text(encoding="utf-8"))
    return [ItemLabel(**d) for d in data]
