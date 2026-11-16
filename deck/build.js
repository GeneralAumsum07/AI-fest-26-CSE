// Builds deck/exposure-self-audit.pptx.
//
// Structure: one theme (THEME), two layouts (DARK for title/close, CONTENT for
// everything else), one section per judging criterion, speaker notes on every
// slide. Diagrams that need flexbox-style layout are pre-rendered PNGs from
// diagrams/render.js; everything with numbers in it (chart, stat callouts,
// persona grid) is native so it stays editable and crisp.
//
// Every number on these slides is copied from a measured result (results/,
// the ledger) or a cited source. Do not round or "tidy" them here: change the
// source, then the slide.
//
// Run: node diagrams/render.js && node build.js [output.pptx]
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");

const SKILL = "C:/Users/Rachit/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/local-agent-mode-sessions/skills-plugin/a2c4b683-6f95-4a80-b01f-8fd8485dc206/72a00f13-b55c-42a6-aaac-fcb2203d0d97/skills/pptx";
const { applyTheme } = require(SKILL + "/scripts/apply_theme.js");

const A = (f) => path.join(__dirname, "assets", f);
// An optional destination lets us produce a revision while PowerPoint holds
// the original open, without closing the user's presentation or losing edits.
const OUT = path.resolve(__dirname, process.argv[2] || "exposure-self-audit.pptx");
const REPO = "https://github.com/GeneralAumsum07/AI-fest-26-CSE";

// Palette. Ink and paper carry ~90% of the deck; the three risk colours are
// the app's own High / Medium / Low, so a colour means the same thing on the
// slide as in the product. Red-orange is the one sharp accent.
const HEX = {
  ink: "15171C", paper: "F3EFE6", ink2: "2A2D35", line: "D9D2C3",
  muted: "6A6E76", high: "E0492F", med: "E39B2B", safe: "3E8E6E",
};
const THEME = {
  name: "Exposure Self-Audit",
  headFontFace: "Bahnschrift",
  bodyFontFace: "Segoe UI",
  colors: {
    dk1: HEX.ink, lt1: HEX.paper, dk2: HEX.ink2, lt2: HEX.line,
    accent1: HEX.high, accent2: HEX.med, accent3: HEX.safe,
    accent4: HEX.muted, accent5: "9AA0A8", accent6: HEX.ink2,
    hlink: HEX.high, folHlink: HEX.muted,
  },
};

const W = 13.333, H = 7.5, MX = 0.6;   // canvas and side margin, inches

// Lucide icon -> base64 PNG in a given colour. Rasterised at 256 px so it
// stays sharp when projected.
async function icon(name, color) {
  let svg = fs.readFileSync(path.join(__dirname, "node_modules/lucide-static/icons", name + ".svg"), "utf8");
  svg = svg.replace(/<!--.*?-->/s, "").replace(/currentColor/g, "#" + color);
  const buf = await sharp(Buffer.from(svg), { density: 600 }).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// Image size helper: keep the file's aspect ratio for a given width.
async function fitW(file, w) {
  const m = await sharp(file).metadata();
  return { w, h: (w * m.height) / m.width };
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "Exposure Self-Audit";
  pres.subject = "AI-FEST 2026, CSE track: Digital Identity Theft";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---- Layouts --------------------------------------------------------------
  pres.defineSlideMaster({
    title: "DARK",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.05, w: 6.9, h: 1.1,
        fontSize: 54, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, MX, 0.6, MX],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.82, w: W - 2 * MX, h: 0.8,
        fontSize: 28, color: C.text1, valign: "top", align: "left", margin: 0 }, text: "" } },
      { text: { text: "Exposure Self-Audit  ·  AI-FEST 2026", options: { x: MX, y: H - 0.45, w: 5, h: 0.25,
        fontSize: 9, color: C.accent4, margin: 0 } } },
    ],
    slideNumber: { x: W - MX - 0.5, y: H - 0.45, w: 0.5, h: 0.25, fontSize: 9, color: C.accent4, align: "right", margin: 0 },
  });

  // The motif: every content slide opens with a "redaction bar" label, the
  // same black bar used to cover leaks in the title visual.
  const kicker = (s, label) => {
    // Bar shape plus a zero-margin text box on top, so the label sits centred
    // in the bar whatever unit pptxgenjs reads a margin array in.
    const w = 0.105 * label.length + 0.4;   // rough width of 10.5 pt caps with 2 pt tracking
    s.addShape(pres.shapes.RECTANGLE, { x: MX, y: 0.42, w, h: 0.3, fill: { color: C.text1 }, objectName: "Kicker bar" });
    s.addText(label, { x: MX + 0.12, y: 0.42, w: w - 0.2, h: 0.3, color: C.background1, fontSize: 10.5, bold: true,
      charSpacing: 2, margin: 0, valign: "middle", isTextBox: true, objectName: "Kicker" });
  };
  const slide = (section, masterName = "CONTENT") => pres.addSlide({ masterName, sectionTitle: section });

  // =========================================================================
  // 1. Title
  // =========================================================================
  pres.addSection({ title: "Opening" });
  {
    const s = slide("Opening", "DARK");
    s.addText("AI-FEST 2026  ·  CSE  ·  DIGITAL IDENTITY THEFT", { x: MX, y: 0.6, w: 7, h: 0.3,
      fontSize: 11, color: C.accent5, charSpacing: 3, margin: 0, isTextBox: true });
    s.addText("Exposure Self-Audit", { placeholder: "title" });
    s.addText("Find what a stranger could build from your Instagram or YouTube, and which posts to change before they do.",
      { x: MX, y: 3.35, w: 6.4, h: 1.2, fontSize: 19, color: "C9C4B8", margin: 0, valign: "top", isTextBox: true });
    s.addText([
      { text: "Runs on your laptop.", options: { bold: true, color: C.background1 } },
      { text: "  Reads your own export, never your messages.", options: { color: "C9C4B8" } },
    ], { x: MX, y: 4.75, w: 6.6, h: 0.4, fontSize: 14, margin: 0, isTextBox: true });

    // Team credit. Sits in the gap above the repo link so the two read as one
    // "who made it / where it lives" block; the tracked small-caps label
    // reuses the top kicker's style instead of introducing a new one.
    s.addText([
      { text: "TEAM  ", options: { color: C.accent5, fontSize: 11, charSpacing: 3 } },
      { text: "GA07", options: { color: C.background1, fontSize: 16, bold: true, charSpacing: 1 } },
    ], { x: MX, y: 5.7, w: 4, h: 0.4, valign: "middle", margin: 0, isTextBox: true, objectName: "Team" });

    // Hero: a made-up post, every leak redacted and tagged with its recipe.
    const p = await fitW(A("post.png"), 4.75);
    s.addImage({ path: A("post.png"), x: W - MX - p.w + 0.1, y: (H - p.h) / 2 + 0.05, w: p.w, h: p.h,
      altText: "A made-up public post. Its away-from-home phrase, family name, phone number, ID number and voice are each covered by a black bar labelled with the scam it enables." });

    s.addImage({ path: A("github.png"), x: MX, y: 6.42, w: 0.42, h: 0.42, hyperlink: { url: REPO },
      altText: "GitHub" });
    s.addText("github.com/GeneralAumsum07/AI-fest-26-CSE", { x: MX + 0.55, y: 6.42, w: 5.5, h: 0.42,
      fontSize: 13, color: C.background1, valign: "middle", margin: 0, isTextBox: true,
      hyperlink: { url: REPO } });
    s.addNotes(
      "One line: this is a check a student runs on their own Instagram or YouTube export before a scammer does the same research. YouTube has passed a real-model end-to-end browser test on a synthetic Takeout archive; real Takeout compatibility is still unverified.\n" +
      "Point at the post: the black bars are what the tool finds. Each one is tagged with the scam it feeds: R1 is a voice-clone call to the family, R3 is a loan or SIM in your name.\n" +
      "Everything in this deck and the demo is synthetic data.");
  }

  // =========================================================================
  // 2. Threat (Innovation)
  // =========================================================================
  pres.addSection({ title: "Threat" });
  {
    const s = slide("Threat");
    kicker(s, "01  THE THREAT");
    s.addText("Scammers build the call to your parents out of your own posts.", { placeholder: "title" });

    // Threat model as a quiet two-column table: labels in caps, hairlines only.
    const rows = [
      ["ATTACKER", "A scammer doing open-source reconnaissance on one person. No hacking, no account access."],
      ["TARGET", "College students with a public Instagram. The people who pay are their family."],
      ["GOAL", "Money (\"Mum, I've had an accident, send money\") or misuse of an ID document."],
      ["METHOD", "Voice from reels, face photos, family names from captions, \"I'm away\" posts, ID numbers in photos."],
      ["OUR DEFENCE", "Show which ingredients the profile supplies, which scams they are enough for, and the smallest set of changes that breaks them."],
      ["STAGE", "Before the attack: exposure."],
    ];
    s.addTable(rows.map(([k, v], i) => [
      { text: k, options: { bold: true, fontSize: 10.5, color: C.accent4, charSpacing: 1.5, valign: "top" } },
      { text: v, options: { fontSize: 13.5, color: C.text1, valign: "top", bold: i === 5 } },
    ]), { x: MX, y: 1.95, w: 6.75, colW: [1.55, 5.2], rowH: 0.62,
      border: [{ type: "solid", pt: 0.75, color: HEX.line }, { type: "none" }, { type: "solid", pt: 0.75, color: HEX.line }, { type: "none" }], margin: [0.07, 0.08, 0.07, 0], fill: { color: HEX.paper },
      objectName: "Threat model" });

    // Evidence column: why "before" — catching the fake during the call fails.
    const stats = [
      ["1 in 5", C.accent1, "of Indians surveyed have already faced a voice-clone scam.", "McAfee press release, 4 Feb 2026 (vendor survey)"],
      ["59.6%", C.text1, "accuracy of voice-clone detectors on replayed audio.", "EchoFake, arXiv 2510.19414"],
      ["55.5%", C.text1, "of the time, people spot a deepfake: close to a coin flip.", "Synthetic Trust Attacks, arXiv 2604.04951"],
    ];
    const sx = 7.75, sw = W - MX - sx, nw = 1.85;
    stats.forEach(([n, col, what, src], i) => {
      const y = 1.95 + i * 1.32;
      s.addText(n, { x: sx, y, w: nw, h: 0.75, fontFace: THEME.headFontFace, fontSize: 36, bold: true,
        color: col, margin: 0, valign: "top", isTextBox: true, objectName: "Stat " + (i + 1) });
      s.addText(what, { x: sx + nw, y: y + 0.05, w: sw - nw, h: 0.75, fontSize: 13, color: C.text1,
        margin: 0, valign: "top", isTextBox: true });
      s.addText(src, { x: sx + nw, y: y + 0.84, w: sw - nw, h: 0.26, fontSize: 9.5, color: C.accent4,
        margin: 0, italic: true, isTextBox: true });
    });
    s.addShape(pres.shapes.RECTANGLE, { x: sx, y: 5.95, w: sw, h: 0.7, fill: { color: C.text1 }, objectName: "Takeaway" });
    s.addText("Spotting the fake on the call doesn't work. So we act before it: remove the ingredients.",
      { x: sx + 0.18, y: 5.95, w: sw - 0.3, h: 0.7, fontSize: 13.5, color: C.background1, valign: "middle",
        margin: 0, isTextBox: true });
    s.addNotes(
      "The attacker needs no hacking: everything comes from public posts.\n" +
      "Why act before the call: detectors fall to 59.6% on replayed audio (EchoFake), people spot deepfakes about 55.5% of the time, and the EchoFake-family papers show English-trained detectors fail on Indic languages.\n" +
      "McAfee figure is a vendor survey: say so if asked. We dropped the national loss figure because the two press reports we found disagree.");
  }

  // =========================================================================
  // 3. How it works (Technical)
  // =========================================================================
  pres.addSection({ title: "How it works" });
  {
    const s = slide("How it works");
    kicker(s, "02  HOW IT WORKS");
    s.addText("Three independent readers, then rules that no model gets to decide.", { placeholder: "title" });
    const d = await fitW(A("pipeline_t.png"), W - 2 * MX);
    s.addImage({ path: A("pipeline_t.png"), x: MX, y: 1.85, w: d.w, h: d.h,
      altText: "Pipeline: Instagram or YouTube export, allowlisted reader, three readers (vision model, rules and text readers, voice), grounding, attack recipes R1 to R3, ranked fixes and a plain report." });

    const points = [
      ["cpu", "Fits an 8 GB laptop GPU", "one model loaded at a time: vision is unloaded before the speaker model starts"],
      ["binary", "Checksums, not guesses", "an ID number only counts if Verhoeff or Luhn passes, because a 4B model misreads digits"],
      ["scale", "Fixes ranked by payoff", "greedy: each pick removes the most harm per unit of effort, ending a risk beats lowering one"],
    ];
    const cw = (W - 2 * MX - 0.6) / 3, py = 1.85 + d.h + 0.5;
    for (let i = 0; i < points.length; i++) {
      const [ic, head, body] = points[i];
      const x = MX + i * (cw + 0.3);
      s.addShape(pres.shapes.OVAL, { x, y: py, w: 0.5, h: 0.5, fill: { color: C.text1 } });
      s.addImage({ data: await icon(ic, HEX.paper), x: x + 0.12, y: py + 0.12, w: 0.26, h: 0.26 });
      s.addText(head, { x: x + 0.65, y: py - 0.02, w: cw - 0.65, h: 0.32, fontFace: THEME.headFontFace,
        fontSize: 15, bold: true, color: C.text1, margin: 0, isTextBox: true });
      s.addText(body, { x: x + 0.65, y: py + 0.32, w: cw - 0.65, h: 0.8, fontSize: 12, color: C.accent4,
        margin: 0, valign: "top", isTextBox: true });
    }
    s.addNotes(
      "Order: Instagram or YouTube export ZIP, platform-specific allowlisted reader, keyframes and audio, vision model on every image, caption reader, unload, rules layer (Presidio + checksums + lexicon), grounding, ingredients, recipes R1 to R3, ranked fixes, redacted wording. YouTube titles and descriptions enter the caption path; its uploaded videos enter the same frame and audio readers.\n" +
      "Qwen3.5 4B via Ollama reads documents and scenes. GLiNER finds names in captions on the CPU. Silero VAD finds speech; SpeechBrain ECAPA checks it is your voice against one enrol sentence.\n" +
      "Grounding: a name or number the model claims must appear in the post's own text or it is dropped. Two readers agreeing is 'confirmed', one is 'likely', none goes to 'Not sure'.\n" +
      "Recipes are data, not model output: three recipes, ten level rules in one function.");
  }

  // =========================================================================
  // 4. Does it work: held-out ablation (Effectiveness)
  // =========================================================================
  pres.addSection({ title: "Results" });
  {
    const s = slide("Results");
    kicker(s, "03  DOES IT WORK");
    s.addText("Only the combined system caught every risky held-out post.", { placeholder: "title" });

    // Source: results/results.md, the single held-out run (40 risky, 43 benign).
    s.addChart(pres.charts.BAR, [
      { name: "Risky posts flagged", labels: ["Rules only", "Vision only", "Text only", "Full system"], values: [35, 60, 38, 100] },
      { name: "Harmless posts flagged", labels: ["Rules only", "Vision only", "Text only", "Full system"], values: [9, 14, 9, 14] },
    ], {
      x: MX, y: 1.8, w: 7.3, h: 4.85, barDir: "col", barGapWidthPct: 55,
      chartColors: [HEX.ink, HEX.high],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 11,
      dataLabelColor: HEX.ink, dataLabelFontFace: "+mn-lt",
      catAxisLabelColor: HEX.ink, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
      catAxisLineShow: true, catAxisLineColor: HEX.ink,
      valAxisHidden: true, valAxisMaxVal: 110, valAxisMinVal: 0,
      valGridLine: { style: "none" }, catGridLine: { style: "none" },
      showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: HEX.ink,
      objectName: "Ablation chart",
    });

    const rx = 8.35, rw = W - MX - rx;
    s.addText("40 / 40", { x: rx, y: 1.85, w: rw, h: 0.8, fontFace: THEME.headFontFace, fontSize: 44, bold: true,
      color: C.text1, margin: 0, isTextBox: true });
    s.addText("risky posts flagged (95% CI 91–100%)", { x: rx, y: 2.62, w: rw, h: 0.3, fontSize: 12.5,
      color: C.text1, margin: 0, isTextBox: true });
    s.addText("6 / 43", { x: rx, y: 3.1, w: rw, h: 0.8, fontFace: THEME.headFontFace, fontSize: 44, bold: true,
      color: C.accent1, margin: 0, isTextBox: true });
    s.addText("harmless posts flagged (14%, CI 7–27%): no worse than vision alone", { x: rx, y: 3.87, w: rw, h: 0.5,
      fontSize: 12.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    s.addShape(pres.shapes.LINE, { x: rx, y: 4.6, w: rw, h: 0, line: { color: HEX.line, width: 1 } });
    s.addText([
      { text: "Why combine: ", options: { bold: true } },
      { text: "each reader alone misses whole categories. Rules miss ID, card, travel, college and face; vision misses phone, family and away.", options: {} },
    ], { x: rx, y: 4.72, w: rw, h: 1.1, fontSize: 12.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    s.addText("83 synthetic Instagram images, run once after every threshold was frozen. A small set, so the intervals are wide.",
      { x: rx, y: 5.95, w: rw, h: 0.6, fontSize: 10, italic: true, color: C.accent4, margin: 0, valign: "top", isTextBox: true });
    s.addNotes(
      "Single held-out run, 40 risky and 43 harmless synthetic images, Wilson 95% intervals.\n" +
      "Rules only 14/40 (22-50%), vision only 24/40 (45-74%), text only 15/40 (24-53%), full 40/40 (91-100%).\n" +
      "Harmless flagged: 4/43, 6/43, 4/43, 6/43. Full system's false alarms by category: ID 3, contact 2, family 2.\n" +
      "The full system also routes 11 findings to 'Not sure' instead of asserting them.");
  }

  // =========================================================================
  // 5. Before / after, voice, speed (Effectiveness, continued)
  // =========================================================================
  {
    const s = slide("Results");
    kicker(s, "03  DOES IT WORK");
    s.addText("Three fixes end the ID risk and drop the voice-call risk to Low.", { placeholder: "title" });

    // Persona grid: the four demo exports, real pipeline, final fix weights.
    const LV = { high: [HEX.high, "HIGH"], medium: [HEX.med, "MEDIUM"], low: [HEX.safe, "LOW"], none: [null, "none"] };
    const personas = [
      ["High exposure", "the demo profile", ["high", "medium", "high"]],
      ["Same profile, fixed", "top three fixes applied", ["low", "medium", "none"]],
      ["Medium exposure", "", ["medium", "low", "none"]],
      ["Careful", "one item left as \"Not sure\"", ["none", "none", "none"]],
    ];
    const gx = MX, gy = 1.95, labW = 2.55, cellW = 1.45, rowH = 0.9;
    ["R1 voice call", "R2 fake profile", "R3 ID misuse"].forEach((h, j) =>
      s.addText(h, { x: gx + labW + j * cellW, y: gy, w: cellW, h: 0.35, fontSize: 11, bold: true,
        color: C.accent4, align: "center", margin: 0, isTextBox: true }));
    personas.forEach(([name, sub, lv], i) => {
      const y = gy + 0.45 + i * rowH;
      if (i === 1) s.addShape(pres.shapes.RECTANGLE, { x: gx - 0.1, y: y - 0.08, w: labW + 3 * cellW + 0.15, h: rowH - 0.04,
        fill: { color: "E7E1D4" }, objectName: "Fixed row highlight" });
      s.addText(name, { x: gx, y, w: labW, h: 0.38, fontFace: THEME.headFontFace, fontSize: 15, bold: true,
        color: C.text1, margin: 0, isTextBox: true });
      if (sub) s.addText(sub, { x: gx, y: y + 0.37, w: labW, h: 0.3, fontSize: 10.5, color: C.accent4, margin: 0, isTextBox: true });
      lv.forEach((l, j) => {
        const [col, label] = LV[l];
        const cx = gx + labW + j * cellW + 0.15;
        s.addText(label, { x: cx, y: y + 0.08, w: cellW - 0.3, h: 0.45, fontSize: 11, bold: true, align: "center",
          valign: "middle", margin: 0, color: col ? "FFFFFF" : C.accent4,
          fill: col ? { color: col } : undefined, line: col ? undefined : { color: HEX.line, width: 1.25, dashType: "dash" },
          shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.06, isTextBox: true });
      });
    });

    // Right column: voice and speed, each with its honest miss.
    const rx = 7.65, rw = W - MX - rx;
    const card = (y, big, bigCol, line1, line2) => {
      s.addText(big, { x: rx, y, w: rw, h: 0.75, fontFace: THEME.headFontFace, fontSize: 40, bold: true,
        color: bigCol, margin: 0, isTextBox: true });
      s.addText(line1, { x: rx, y: y + 0.75, w: rw, h: 0.55, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true });
      s.addText(line2, { x: rx, y: y + 1.3, w: rw, h: 0.5, fontSize: 11, color: C.accent4, margin: 0, valign: "top", isTextBox: true });
    };
    card(1.9, "9 / 10", C.text1, "test clips put in the right voice band (95% CI 60–98%), mean error 1.05 s of speech.",
      "Miss: another speaker's voice was credited for 4.5 s.");
    card(4.05, "~4 min", C.text1, "for a typical 40-item profile on a laptop RTX 5060: about 4 s a photo, 30 s a long reel.",
      "Miss: a profile of only long reels takes about 20 minutes.");
    s.addNotes(
      "Persona results use the real pipeline and the final fix weights; 12 of 12 persona checks pass.\n" +
      "High persona's top fixes: delete the ID post, then archive the reel. That ends R3 and drops R1 to low. R2 stays medium because face photos and the name remain, and R2 is capped at medium by design.\n" +
      "Voice: 10 reserved test clips, run once. Speed: 100 dev items took 588 s; the cap is 40 items, newest first, and the rest are listed as not checked, never silently dropped.");
  }

  // =========================================================================
  // 6. YouTube verification. These are smoke-test observations, kept separate
  // from the frozen held-out accuracy and voice-band evaluation above.
  // Source: docs/evidence/youtube-e2e/verification.md and summary.json, 16 Nov 2026.
  // Native text and shapes keep the measured counts editable in PowerPoint.
  // =========================================================================
  {
    const s = slide("Results");
    kicker(s, "03  YOUTUBE VERIFIED");
    s.addText("YouTube works end to end with the real local models.", { placeholder: "title" });

    const checks = [
      ["file-archive", "Upload and decode", "Browser upload of a synthetic Takeout ZIP; actual MP4 frames and AAC speech decoded."],
      ["cpu", "Production readers", "Qwen3.5 4B, GLiNER, Presidio, Silero VAD and ECAPA. No simulated model responses."],
      ["shield-check", "Report and privacy", "ID, contact, family and away findings. Extracted details redacted; hidden videos blocked."],
      ["check-check", "Feedback and deletion", "Remove the contact finding: phone-call risk drops High to Medium. Forget the run: report returns 404."],
    ];
    for (let i = 0; i < checks.length; i++) {
      const [ic, head, body] = checks[i];
      const y = 1.95 + i * 1.1;
      s.addShape(pres.shapes.OVAL, { x: MX, y, w: 0.52, h: 0.52, fill: { color: C.text1 } });
      s.addImage({ data: await icon(ic, HEX.paper), x: MX + 0.12, y: y + 0.12, w: 0.28, h: 0.28 });
      s.addText(head, { x: MX + 0.75, y: y - 0.02, w: 5.65, h: 0.34, fontFace: THEME.headFontFace,
        fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true });
      s.addText(body, { x: MX + 0.75, y: y + 0.34, w: 5.65, h: 0.68, fontSize: 12.5,
        color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }

    const px = 7.75, pw = W - MX - px;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: px, y: 1.95, w: pw, h: 4.55,
      fill: { color: C.text1 }, rectRadius: 0.08, objectName: "YouTube verification results" });
    s.addText("2 of 4", { x: px + 0.35, y: 2.23, w: pw - 0.7, h: 0.75,
      fontFace: THEME.headFontFace, fontSize: 42, bold: true, color: C.background1, margin: 0, isTextBox: true });
    s.addText("videos audited; the 2 marked private or unlisted were excluded", { x: px + 0.35, y: 3.02,
      w: pw - 0.7, h: 0.65, fontSize: 14, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    s.addText("10.6 s", { x: px + 0.35, y: 3.93, w: pw - 0.7, h: 0.75,
      fontFace: THEME.headFontFace, fontSize: 42, bold: true, color: C.background1, margin: 0, isTextBox: true });
    s.addText("of matching speech in the enrolled voice", { x: px + 0.35, y: 4.72,
      w: pw - 0.7, h: 0.65, fontSize: 14, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    s.addText("SYNTHETIC MEDIA  /  16 NOV 2026", { x: px + 0.35, y: 5.85, w: pw - 0.7, h: 0.3,
      fontSize: 10, bold: true, charSpacing: 1, color: C.accent5, margin: 0, isTextBox: true });
    s.addText("End-to-end verification on synthetic media. Real Takeout compatibility and YouTube held-out accuracy remain unverified.",
      { x: MX, y: 6.62, w: W - 2 * MX, h: 0.3, fontSize: 10.5, italic: true,
        color: C.accent4, margin: 0, isTextBox: true });
    s.addNotes(
      "Source: docs/evidence/youtube-e2e/verification.md and summary.json in the repo, 16 November 2026. This was a browser-driven production-pipeline check, separate from the frozen Instagram held-out evaluation.\n" +
      "Two public videos and two videos marked private/unlisted, all synthetic. The risky public video showed a generated mock ID and had contact, family and away phrases in its description. The second public video was neutral and produced no asserted finding.\n" +
      "Every model was real: Qwen3.5 4B through Ollama, GLiNER, Presidio, Silero VAD and SpeechBrain ECAPA. Matching synthetic speech counted for 10.6 seconds, moderate band, against a separately generated enrolment sentence.\n" +
      "Verified report rendering, ranked fixes, public thumbnails, hidden-media 404s, redaction, offline wording, feedback recomputation and deletion. Removing the contact finding lowered R1 from High to Medium; forgetting removed the run. The default suite also passed 203 tests.\n" +
      "Limits: the Takeout layout and headers were guessed; no real Google Takeout has been checked. Missing or unknown visibility is included. That run showed the same ID once per video frame; this was fixed afterwards (one finding per video and category). A live re-check with the real models then showed the ID once instead of five times, with every other check unchanged (docs/evidence/youtube-e2e/recheck-summary.json). No model thresholds or held-out numbers changed.");
  }

  // =========================================================================
  // 7. Privacy and misuse
  // =========================================================================
  pres.addSection({ title: "Privacy" });
  {
    const s = slide("Privacy");
    kicker(s, "04  PRIVACY AND MISUSE");
    s.addText("A tool about leaks that does not leak, and does not help the attacker.", { placeholder: "title" });
    const rows = [
      ["book-open", "Read", "Instagram profile and media indexes; YouTube channel and video metadata; allowed photos and videos."],
      ["ban", "Never opened", "Messages, contacts, searches, ad data; YouTube history, comments and subscriptions."],
      ["trash-2", "Kept", "Nothing. The temp folder is wiped on exit; the voice clip stays in memory."],
      ["wifi-off", "Sent", "Nothing by default. If online wording is switched on, only a redacted payload, shown in the app first. The server listens on loopback only."],
    ];
    for (let i = 0; i < rows.length; i++) {
      const [ic, k, v] = rows[i];
      const y = 1.95 + i * 1.12;
      s.addShape(pres.shapes.OVAL, { x: MX, y, w: 0.55, h: 0.55, fill: { color: C.text1 } });
      s.addImage({ data: await icon(ic, HEX.paper), x: MX + 0.14, y: y + 0.14, w: 0.27, h: 0.27 });
      s.addText(k, { x: MX + 0.75, y: y - 0.02, w: 5.6, h: 0.32, fontFace: THEME.headFontFace, fontSize: 16, bold: true,
        color: C.text1, margin: 0, isTextBox: true });
      s.addText(v, { x: MX + 0.75, y: y + 0.32, w: 5.75, h: 0.72, fontSize: 12.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }
    // Misuse panel on ink: the one dark block on the slide carries the
    // "what an attacker gets" answer, with the unsolved case kept honest.
    const px = 7.55, pw = W - MX - px;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: px, y: 1.95, w: pw, h: 4.65, fill: { color: C.text1 }, rectRadius: 0.08,
      objectName: "Misuse panel" });
    s.addText("If an attacker runs it", { x: px + 0.35, y: 2.15, w: pw - 0.7, h: 0.4, fontFace: THEME.headFontFace,
      fontSize: 18, bold: true, color: C.background1, margin: 0, isTextBox: true });
    const guards = [
      "It needs the owner's own export: there is no username box and no scraping.",
      "It outputs fixes, not a fact sheet: values never reach the screen, the log or the wording model.",
      "No scam scripts, no voice cloning.",
    ];
    for (let i = 0; i < guards.length; i++) {
      const y = 2.75 + i * 0.78;
      s.addImage({ data: await icon("shield-check", HEX.paper), x: px + 0.35, y: y + 0.02, w: 0.28, h: 0.28 });
      s.addText(guards[i], { x: px + 0.8, y, w: pw - 1.15, h: 0.7, fontSize: 12.5, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    }
    s.addShape(pres.shapes.RECTANGLE, { x: px + 0.35, y: 5.15, w: pw - 0.7, h: 1.2, fill: { color: C.text2 },
      line: { color: HEX.high, width: 1.5 } });
    s.addText([
      { text: "Unsolved. ", options: { bold: true, color: HEX.high } },
      { text: "Someone could hand-build a fake export from scraped photos. That raises their effort; it does not stop them.", options: { color: C.background1 } },
    ], { x: px + 0.55, y: 5.15, w: pw - 1.1, h: 1.2, fontSize: 12.5, margin: 0, valign: "middle", isTextBox: true });
    s.addNotes(
      "Logging rule in the code: counts and timings only, never a caption, value or file name.\n" +
      "A leak check runs before anything is shown or sent: every secret found in the export is searched for in the outgoing payload.\n" +
      "Be upfront about the unsolved case; it is on the slide on purpose.");
  }

  // =========================================================================
  // 8. Using it, limits
  // =========================================================================
  pres.addSection({ title: "Using it" });
  {
    const s = slide("Using it");
    kicker(s, "05  USING IT");
    s.addText("A plain report, a fix order, and a card for the family.", { placeholder: "title" });

    // Two crops of the real report (high persona), stacked on an ink frame so
    // the app's dark UI reads as one screenshot rather than two pasted images.
    const fw = 6.35, fx = MX, fy = 1.85;
    const t = await fitW(A("shot_top.png"), fw - 0.3), d = await fitW(A("shot_id.png"), fw - 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: fx, y: fy, w: fw, h: t.h + d.h + 0.45, fill: { color: "17171B" },
      rectRadius: 0.06, objectName: "Screenshot frame" });
    s.addImage({ path: A("shot_top.png"), x: fx + 0.15, y: fy + 0.15, w: t.w, h: t.h,
      altText: "Report header: what a stranger can build from your profile; 9 posts read; 3 ways someone could misuse what you posted." });
    s.addImage({ path: A("shot_id.png"), x: fx + 0.15, y: fy + 0.3 + t.h, w: d.w, h: d.h,
      altText: "A High risk card: misuse of your ID document, with an Aadhaar-format number in post 5 and a phone number in post 6, each with a This is wrong button, and advice to take the post down." });
    s.addText("The high-risk demo profile. Every finding has \"This is wrong\"; the report recomputes at once.",
      { x: fx, y: fy + t.h + d.h + 0.55, w: fw, h: 0.4, fontSize: 10.5, italic: true, color: C.accent4, margin: 0, isTextBox: true });

    const rx = 7.35, rw = W - MX - rx;
    const c = await fitW(A("shot_card.png"), rw);
    s.addImage({ path: A("shot_card.png"), x: rx, y: fy, w: c.w, h: c.h,
      altText: "Printable family safety card: agree a code word in person; hang up and call back; nobody genuine needs your OTP; report fraud on 1930 or cybercrime.gov.in." });
    const ly = fy + c.h + 0.35;
    s.addText("Limits", { x: rx, y: ly, w: rw, h: 0.35, fontFace: THEME.headFontFace, fontSize: 16, bold: true,
      color: C.text1, margin: 0, isTextBox: true });
    const limits = [
      "Finds exposures; it cannot prove a scam was prevented.",
      "Tested on synthetic data; intervals are wide.",
      "Voice thresholds are heuristics.",
      "A 4B model misreads digits (checksums catch most).",
      "YouTube passed the synthetic end-to-end check; real Takeout compatibility is unverified.",
    ];
    s.addText(limits.map((l, i) => ({ text: l, options: { bullet: true, breakLine: i < limits.length - 1 } })),
      { x: rx, y: ly + 0.4, w: rw, h: 2.0, fontSize: 12.5, color: C.text1, margin: 0, valign: "top",
        paraSpaceAfter: 5, isTextBox: true });
    s.addNotes(
      "Live demo goes here: upload the high persona, read the top card, then the fixed persona to show the levels drop.\n" +
      "The safety card prints on one page and is meant for parents who will never open the app.\n" +
      "'Not sure' findings are listed separately and never raise a risk level on their own.");
  }

  // =========================================================================
  // 9. What's next: more platforms, and the safe form of "scan my profile"
  // =========================================================================
  pres.addSection({ title: "Next" });
  {
    const s = slide("Next");
    kicker(s, "06  WHAT'S NEXT");
    s.addText("Next: more platforms, one export reader each.", { placeholder: "title" });

    // Left: one row per platform group. The status chip reuses the risk-chip
    // shape and palette from slide 5, so "built / next / later / no" reads in
    // the deck's existing colour language rather than a new legend.
    const rows = [
      // Synthetic end-to-end verification does not establish real-export
      // compatibility or replace a held-out accuracy evaluation.
      ["BUILT", HEX.safe, true, "Instagram, YouTube", "Both verified end to end with real models on synthetic data. YouTube: real Takeout compatibility and held-out accuracy still unverified."],
      ["NEXT", HEX.med, true, "LinkedIn", "A new export reader and allowlist. The photo, text and voice readers, recipes and report are reused."],
      ["LATER", HEX.muted, false, "Reddit", "Mostly text. Comment history can give away a city or a college."],
      ["NO", HEX.high, false, "Discord, Snapchat", "Mostly private messages, and the app never reads messages."],
    ];
    for (let i = 0; i < rows.length; i++) {
      const [chip, col, filled, name, desc] = rows[i];
      const y = 1.95 + i * 1.12;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y, w: 1.05, h: 0.4, rectRadius: 0.06,
        fill: filled ? { color: col } : { color: HEX.paper }, line: { color: col, width: 1.5 }, objectName: `Status ${chip}` });
      s.addText(chip, { x: MX, y, w: 1.05, h: 0.4, fontSize: 11, bold: true, charSpacing: 1, align: "center", valign: "middle",
        color: filled ? C.background1 : col, margin: 0, isTextBox: true });
      s.addText(name, { x: MX + 1.3, y: y - 0.02, w: 5.3, h: 0.32, fontFace: THEME.headFontFace, fontSize: 16, bold: true,
        color: C.text1, margin: 0, isTextBox: true });
      s.addText(desc, { x: MX + 1.3, y: y + 0.32, w: 5.3, h: 0.7, fontSize: 12.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }

    // Right: the "paste a link" idea in the only form that does not hand an
    // attacker a reconnaissance tool. Same ink panel as the misuse slide, on
    // purpose: both answer "what if the wrong person uses it".
    const px = 7.55, pw = W - MX - px;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: px, y: 1.95, w: pw, h: 4.65, fill: { color: C.text1 }, rectRadius: 0.08,
      objectName: "Stranger view panel" });
    s.addImage({ data: await icon("scan-eye", HEX.paper), x: px + 0.35, y: 2.2, w: 0.38, h: 0.38 });
    s.addText("See what a stranger sees", { x: px + 0.85, y: 2.18, w: pw - 1.2, h: 0.42, fontFace: THEME.headFontFace,
      fontSize: 18, bold: true, color: C.background1, valign: "middle", margin: 0, isTextBox: true });
    s.addText("Audit the public view of a profile, not the export: closer to what an attacker actually gets.",
      { x: px + 0.35, y: 2.75, w: pw - 0.7, h: 0.65, fontSize: 12.5, color: "C9C4B8", margin: 0, valign: "top", isTextBox: true });
    const steps = [
      ["key-round", "Only for accounts you prove you own: sign in with the platform, or put a one-time code in your bio."],
      ["badge-check", "Starts with YouTube and Reddit, through their public APIs. No scraping."],
      ["ban", "No box for someone else's username. Ever."],
    ];
    for (let i = 0; i < steps.length; i++) {
      const y = 3.6 + i * 0.78;
      s.addImage({ data: await icon(steps[i][0], HEX.paper), x: px + 0.35, y: y + 0.02, w: 0.28, h: 0.28 });
      s.addText(steps[i][1], { x: px + 0.8, y, w: pw - 1.15, h: 0.7, fontSize: 12.5, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    }
    s.addText("Not built yet.", { x: px + 0.35, y: 6.05, w: pw - 0.7, h: 0.35, fontSize: 11, italic: true, color: C.accent5,
      margin: 0, isTextBox: true });
    s.addNotes(
      "Instagram and YouTube are built and verified end to end with real local models on synthetic data. YouTube's 16 November 2026 browser check verified upload, video and speech decoding, model inference, report rendering, exclusions, redaction, feedback and deletion. The Takeout layout is still guessed and has not been checked against a real archive; YouTube has not had a held-out accuracy evaluation. Videos marked private or unlisted are skipped; missing or unknown visibility is included. Everything else on this slide is a plan.\n" +
      "Why one reader per platform: each export has its own format and its own private parts, so the 'never opens your messages' allowlist is rebuilt per platform. The models, recipes and report do not change.\n" +
      "Why not just paste a link: anyone could paste anyone's link, which turns a self-audit into reconnaissance on strangers. Proving ownership first is what keeps it a self-audit.\n" +
      "API access per platform still needs checking before building; Instagram's API, for example, covers business and creator accounts only.");
  }

  // =========================================================================
  // 10. Close: repo and credits
  // =========================================================================
  pres.addSection({ title: "Close" });
  {
    const s = slide("Close", "DARK");
    s.addText("Read the code.", { placeholder: "title" });
    s.addImage({ path: A("github.png"), x: MX, y: 3.45, w: 0.8, h: 0.8, hyperlink: { url: REPO }, altText: "GitHub" });
    // pptxgenjs writes a broken relationship id (rIdundefined) when a
    // hyperlink sits on a box made of several runs, so each run carries it.
    s.addText([
      { text: "github.com/", options: { color: "C9C4B8", hyperlink: { url: REPO } } },
      { text: "GeneralAumsum07/AI-fest-26-CSE", options: { color: C.background1, bold: true, hyperlink: { url: REPO } } },
    ], { x: MX + 1.0, y: 3.45, w: 6.4, h: 0.8, fontSize: 20, valign: "middle", margin: 0, isTextBox: true });
    s.addText("Everything in this deck and the demo is synthetic data.", { x: MX, y: 4.6, w: 6.5, h: 0.35,
      fontSize: 13, color: "C9C4B8", margin: 0, isTextBox: true });

    // Credits, as a quiet column on the right.
    const cx = 7.9, cw = W - MX - cx;
    const credits = [
      ["MODELS", "Qwen3.5 (Alibaba, Apache-2.0) · GLiNER PII (Apache-2.0) · SpeechBrain ECAPA (Apache-2.0) · Silero VAD"],
      ["LIBRARIES", "Presidio · spaCy · FastAPI · PyTorch · PyAV · Ollama"],
      ["FORMAT FACTS", "Timelinize importer (AGPL): facts only, no code"],
      ["PRIOR ART", "Visual Privacy Advisor (2017) · PrivAR (2026) · consumer footprint checkers · Thamba · Satark"],
      ["TOOLS", "An AI coding assistant was used for planning and coding."],
    ];
    credits.forEach(([k, v], i) => {
      const y = 1.1 + i * 1.08;
      s.addText(k, { x: cx, y, w: cw, h: 0.28, fontSize: 10, bold: true, charSpacing: 2, color: C.accent1, margin: 0, isTextBox: true });
      s.addText(v, { x: cx, y: y + 0.3, w: cw, h: 0.7, fontSize: 12, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    });
    s.addNotes("Close on the repo link. Questions.");
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
