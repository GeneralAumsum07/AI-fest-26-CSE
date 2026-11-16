// The page talks only to this laptop's own server (same origin, loopback).
// Plain DOM code with no framework: one file the judges can read, and nothing
// to download, so the app works with Wi-Fi off.
"use strict";

const $ = (id) => document.getElementById(id);
let auditId = null;
let recorded = null;          // a Blob from the microphone, if the user recorded one
let missedPost = null;        // the post the "You missed something" dialog is about
// "Try a fix": which fixes are ticked (positions in the current report's fix
// list) and the server's answer for them. Both are page state only; the audit
// on the server never changes, so clearing them restores the real report.
let lastBody = null;
let tried = new Set();
let preview = null;          // {recipes, text} from POST /preview, or null

// Words, not codes. Bands only: the report never shows a score or a percentage.
const LEVEL = { high: "High", medium: "Medium", low: "Low" };
const CATEGORY = {
  ID_DOCUMENT: "an ID document", FINANCIAL: "a bank card or account detail", TRAVEL_DOC: "a ticket or boarding pass",
  CONTACT: "a phone number or email", FAMILY_RELATION: "a family member's name", AWAY_STATUS: "that you are away",
  INSTITUTION: "your college or workplace", FACE_CLEAR: "a clear photo of your face", VOICE: "your voice",
};
const REASON = {
  missing_file: "the file was not in the export", outside_export: "it pointed outside the export",
  not_public: "marked private or unlisted; excluded from the audit",
  over_limit: "over the reading limit", unreadable_video: "the video could not be read",
  unreadable_audio: "the video's sound could not be read",
  unreadable: "the file could not be read", unsupported_type: "this file type is not supported",
  model_error: "the image reader failed on it", model_output: "the image reader's answer made no sense",
  out_of_memory: "the laptop ran out of memory on it", caption_error: "the caption reader failed on it",
  pattern_error: "the number checker failed on it", voice_error: "the voice check failed on it",
  // LinkedIn and Reddit exports list a post's photo by URL only; the app never goes online to fetch it.
  media_not_in_export: "it had a photo or video the export does not include; check that one yourself",
};
const PLATFORM_NAME = { instagram: "Instagram", youtube: "YouTube", linkedin: "LinkedIn", reddit: "Reddit" };
// What the audit opens on each platform, for the privacy receipt's note.
const ACCESS_NOTE = {
  instagram: "The audit opens the profile file, the lists of your posts, and the photos and videos those lists name. It cannot open anything else.",
  youtube: "The audit opens the channel file, the lists of your videos, and the videos those lists name. It cannot open anything else.",
  linkedin: "The audit opens four files: your profile, jobs, education and posts. Messages, connections and the email and phone on your account are never opened.",
  reddit: "The audit opens two files: your posts and your comments, without their IP addresses. Messages, chat, votes and saved items are never opened.",
};
const STAGE = { images: "Looking at photos and video frames", captions: "Reading captions", voice: "Listening for your voice" };

function show(view) {
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== view;
  $("card").hidden = view === "progress" || view === "failed";
}

// The server's labels count from the newest post ("post 1" = newest), the same
// numbering the fix text uses. Never the caption: captions can hold the very
// details being flagged.
let labels = {};
function postName(id) {
  const label = labels[id] || id;
  return label.charAt(0).toUpperCase() + label.slice(1);
}

// The posts behind one recipe: findings in its categories, plus the reels that
// carry the user's voice. (look_at is not this: it lists the unsure finding
// ids behind a "Not sure" recipe.)
function recipePosts(rec, r) {
  const cats = new Set([...rec.has, ...rec.amplifiers]);
  const findings = r.findings.filter((f) => cats.has(f.category));
  const unsure = r.unsure.filter((f) => (rec.look_at || []).includes(f.finding_id));
  const posts = [...findings, ...unsure].map((f) => f.post_id);
  if (cats.has("VOICE")) posts.push(...Object.keys(r.voice.seconds_by_post));
  return { findings: [...findings, ...unsure], posts: [...new Set(posts)] };
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k);
  return e;
}

function thumbs(postIds) {
  const box = el("div", { class: "thumbs" });
  for (const id of [...new Set(postIds)]) {
    box.append(el("figure", { class: "thumb" },
      el("img", { src: `/api/audits/${auditId}/media/${encodeURIComponent(id)}/0`, alt: postName(id), loading: "lazy" }),
      el("figcaption", {}, postName(id), " ",
        el("button", { class: "link", type: "button", onclick: () => openMissed(id) }, "Add a finding"))));
  }
  return box;
}

function toggleThumbs(button, postIds) {
  // Thumbnails load only when asked for: the report itself never shows a photo unprompted.
  const next = button.nextElementSibling;
  if (next && next.classList.contains("thumbs")) { next.remove(); return; }
  button.after(thumbs(postIds));
}

function findingLine(f) {
  return el("li", { class: "finding" },
    el("span", {}, f.what, el("span", { class: "post-reference" }, postName(f.post_id))),
    el("button", { class: "link", type: "button", onclick: () => feedback({ kind: "wrong", finding_id: f.finding_id }) },
      "Mark incorrect"));
}

function render(body) {
  lastBody = body;
  const r = body.report, t = body.text;
  // In a preview the cards show the "after" levels, worded by the same server
  // path as the real report; everything else on the page stays the real report.
  const after = preview ? Object.fromEntries(preview.recipes.map((p) => [p.recipe_id, p])) : null;
  const pt = preview ? preview.text : t;
  // YouTube has no private account, only private videos, and calls items videos.
  const youtube = r.platform === "youtube";
  const item = youtube ? "video" : "post";
  labels = body.post_labels || {};
  const nCouldnt = r.couldnt_check.length;
  // Same item word as the fix text and the chips, so one screen never says both "post" and "video".
  $("counts").textContent = `${r.posts_read} ${item}${r.posts_read === 1 ? "" : "s"} analysed · ` +
    `${nCouldnt} item${nCouldnt === 1 ? "" : "s"} excluded or unavailable`;
  $("summary").textContent = pt.summary;
  $("preview-banner").hidden = !preview;
  $("preview-text").textContent = "Preview. This shows your report after the changes you ticked. " +
    `Nothing has been changed on ${PLATFORM_NAME[r.platform] || "Instagram"}. You still need to make these changes yourself.`;
  $("voice-note").hidden = !body.voice_note;
  $("voice-note").textContent = body.voice_note || "";
  $("private-banner").hidden = !r.is_private;
  $("private-banner").textContent = "Your account is private. Only your followers can see these posts, but any follower can save them.";

  // One card per recipe that applies, worst first (the server already sorted them).
  const box = $("recipes");
  box.replaceChildren();
  for (const rec of r.recipes) {
    if (!rec.level && !rec.not_sure) continue;
    // Cards stay in the real report's order during a preview, so a judge can
    // see the same card change rather than the list reshuffling under them.
    const now = after ? after[rec.recipe_id] : rec;
    const gone = after && (!now || (!now.level && !now.not_sure));
    const words = (!gone && pt.recipes[rec.recipe_id]) || t.recipes[rec.recipe_id] ||
      { title: rec.recipe_id, reasons: "", advice: "" };
    const band = (x) => (x.not_sure ? "Needs review" : LEVEL[x.level]);
    let lvl = rec.not_sure ? ["unsure", "Needs review"] : [rec.level, LEVEL[rec.level]];
    if (gone) lvl = ["ended", `${band(rec)} → None`];
    else if (after && band(now) !== band(rec)) lvl = [now.not_sure ? "unsure" : now.level, `${band(rec)} → ${band(now)}`];
    if (gone) {
      box.append(el("article", { class: "recipe ended" },
        el("div", { class: "recipe-heading" }, el("h3", {}, words.title), el("span", { class: "level ended" }, lvl[1])),
        el("p", {}, "No longer possible with these changes.")));
      continue;
    }
    const { findings, posts: looked } = recipePosts(rec, r);
    const steps = (body.next_steps || {})[rec.recipe_id] || [];
    const btn = el("button", { class: "link", type: "button" },
      looked.length === 1 ? `See the ${item}` : `See the ${looked.length} ${item}s`);
    btn.addEventListener("click", () => toggleThumbs(btn, looked));
    box.append(el("article", { class: "recipe" },
      el("div", { class: "recipe-heading" }, el("h3", {}, words.title), el("span", { class: `level ${lvl[0]}` }, lvl[1])),
      el("p", {}, words.reasons),
      findings.length ? el("ul", { class: "findings" }, ...findings.map(findingLine)) : null,
      words.advice ? el("p", { class: "advice" }, words.advice) : null,
      // Fixed steps from the server (official services, checked by hand); never reworded.
      steps.length ? el("ol", { class: "next-steps" }, ...steps.map((s) => el("li", {}, s))) : null,
      looked.length ? btn : null));
  }
  if (!box.children.length) box.append(el("article", { class: "recipe empty-report" },
    el("h3", {}, "No assessed misuse scenarios identified"),
    el("p", {}, "No matching scenario was found in the content analysed. This does not rule out other exposure or misuse.")));

  fill("unsure", r.unsure, (f) => {
    const li = findingLine(f);
    const b = el("button", { class: "link", type: "button" }, "Have a look");
    b.addEventListener("click", () => toggleThumbs(b, [f.post_id]));
    li.append(b);
    return li;
  });
  fill("past", r.past_exposure, findingLine);
  fill("couldnt", r.couldnt_check, (s) => el("li", {}, `${postName(s.ref.split("/")[0])}: ${REASON[s.reason] || s.reason}`));

  const fixes = $("fixes");
  fixes.replaceChildren();
  r.fixes.forEach((fx, i) => {
    const btn = el("button", { class: "link", type: "button" }, `See the ${item}${fx.post_ids.length === 1 ? "" : "s"}`);
    btn.addEventListener("click", () => toggleThumbs(btn, fx.post_ids));
    // The list supplies its own accessible numbering. Strip the plain-text
    // prefix used by offline templates to avoid rendering each rank twice.
    const text = (t.fixes[i] || `${fx.action} ${fx.post_ids.map(postName).join(", ")}`).replace(/^\d+\.\s*/, "");
    // "Try this" asks the server what the report would say after the fix;
    // nothing is changed on the platform or in the audit.
    const box = el("input", { type: "checkbox", id: `try-${i}` });
    box.checked = tried.has(i);
    box.addEventListener("change", () => { box.checked ? tried.add(i) : tried.delete(i); runPreview(); });
    fixes.append(el("li", {}, text, " ", btn,
      el("label", { class: "try-fix", for: `try-${i}` }, box, "Try this")));
  });
  if (!r.fixes.length) fixes.append(el("li", { class: "note" }, "Nothing to fix first."));

  const lower = r.private_would_lower || [];
  // LinkedIn and Reddit have no private-account switch, so the line would suggest something impossible.
  const canGoPrivate = r.platform === "instagram" || youtube;
  $("private-lower").hidden = !lower.length || !canGoPrivate;
  $("private-lower").textContent = (youtube ? "Setting your public videos to Private would lower: "
                                             : "Switching your account to private would lower: ") +
    lower.map((id) => (t.recipes[id] || { title: id }).title).join("; ") + ".";

  // The privacy receipt: counts and fixed labels from the server, never a
  // file or folder name (message folders are named after people).
  const acc = r.access;
  $("access-panel").hidden = !acc;
  if (acc) {
    const n = (x) => x.toLocaleString("en-IN");
    const row = (label, value, cls = "") => [el("dt", { class: cls }, label), el("dd", { class: cls }, n(value))];
    const never = acc.total - acc.opened;
    $("access-list").replaceChildren(
      ...row("Files in your export", acc.total), ...row("Opened for this audit", acc.opened),
      ...row("Never opened", never), ...acc.never_opened.flatMap((g) => row(g.label, g.count, "sub")));
    $("access-note").textContent = ACCESS_NOTE[r.platform] || ACCESS_NOTE.instagram;
  }

  // The family card: what a caller might know, as fixed category lines. Never
  // a value, so a printed card that is lost gives nothing away.
  const knows = body.caller_knows || [];
  $("caller-block").hidden = !knows.length;
  $("caller-list").replaceChildren(...knows.map((line) => el("li", {}, line)));

  $("sent-line").textContent = body.sent_to_cloud
    ? "This summary was sent to the online wording service. It holds categories and counts only."
    : "Nothing was sent. This is what would be sent if online wording were on.";
}

function fill(id, items, line) {
  $(id).replaceChildren(...items.map(line));
  $(`${id}-group`).hidden = !items.length;
}

async function runPreview() {
  const runId = auditId;
  if (!tried.size) { preview = null; render(lastBody); return; }
  const res = await fetch(`/api/audits/${runId}/preview`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fixes: [...tried] }) });
  if (runId !== auditId) return;
  // On any error fall back to the real report rather than a stale preview.
  preview = res.ok ? await res.json() : null;
  if (!preview) tried.clear();
  render(lastBody);
}

function clearPreview() { tried = new Set(); preview = null; }
$("clear-preview").addEventListener("click", () => { clearPreview(); render(lastBody); });

async function feedback(body) {
  // Feedback re-ranks the fixes, so ticked positions would point at different
  // fixes afterwards: drop the preview first.
  clearPreview();
  const res = await fetch(`/api/audits/${auditId}/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (res.ok) render(await res.json());   // the report updates in place, no reload
}

function openMissed(postId) {
  missedPost = postId;
  $("missed-dialog").showModal();
}

$("missed-dialog").addEventListener("close", () => {
  if ($("missed-dialog").returnValue === "ok" && missedPost)
    feedback({ kind: "missed", post_id: missedPost, category: $("missed-cat").value });
});

async function poll() {
  // A response from a forgotten run must not bring its report back on screen.
  const runId = auditId;
  try {
    const response = await fetch(`/api/audits/${runId}/progress`);
    if (!response.ok) throw new Error("The audit is no longer available. Choose the export again to start a new run.");
    const p = await response.json();
    if (runId !== auditId) return;
    if (p.error) { $("error").textContent = p.error; show("failed"); return; }
    if (!p.finished) {
      $("stage").textContent = `${STAGE[p.stage] || "Opening your export"}${p.total ? ` · ${p.done} of ${p.total}` : ""}`;
      $("bar").max = p.total || 1; $("bar").value = p.done;
      setTimeout(poll, 500);
      return;
    }
    const reportResponse = await fetch(`/api/audits/${runId}/report`);
    if (!reportResponse.ok) throw new Error("The report could not be loaded. Choose the export again to retry.");
    const body = await reportResponse.json();
    if (runId !== auditId) return;
    clearPreview();
    render(body);
    show("report");
  } catch (error) {
    if (runId !== auditId) return;
    $("error").textContent = error.message || "The local app could not be reached. Check that it is running and try again.";
    show("failed");
  }
}

// Keep the native file input and validation for keyboard and screen-reader
// users; the styled drop target is only another way to select that same file.
function updateExportSelection() {
  const file = $("export").files[0];
  const isZip = !file || /\.zip$/i.test(file.name);
  $("export").setCustomValidity(isZip ? "" : "Choose an Instagram, YouTube, LinkedIn or Reddit export in ZIP format.");
  $("export-name").textContent = file ? file.name : "Choose a ZIP file";
  $("export-detail").textContent = file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · selected on this device` : "or drag and drop it here";
  $("drop-zone").classList.toggle("has-file", Boolean(file));
}
$("export").addEventListener("change", updateExportSelection);
for (const name of ["dragenter", "dragover"]) $("drop-zone").addEventListener(name, (event) => {
  event.preventDefault(); $("drop-zone").classList.add("drag-over");
});
for (const name of ["dragleave", "drop"]) $("drop-zone").addEventListener(name, (event) => {
  event.preventDefault(); $("drop-zone").classList.remove("drag-over");
});
$("drop-zone").addEventListener("drop", (event) => {
  if (!event.dataTransfer.files.length) return;
  $("export").files = event.dataTransfer.files;
  updateExportSelection();
});

$("pick").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  form.append("export", $("export").files[0]);
  const enrol = recorded || $("enrol").files[0];
  if (enrol) form.append("enrol", enrol, recorded ? "voice.webm" : enrol.name);
  show("progress");
  try {
    const res = await fetch("/api/audits", { method: "POST", body: form });
    if (!res.ok) throw new Error("The export could not be uploaded. Check the ZIP file and try again.");
    auditId = (await res.json()).id;
    location.hash = `audit=${auditId}`;
    poll();
  } catch (error) {
    $("error").textContent = error.message || "The local app could not be reached. Check that it is running and try again.";
    show("failed");
  }
});

$("rec").addEventListener("click", async () => {
  // About 8 seconds, then stop on its own; the browser asks for the microphone itself.
  try {
    $("rec").disabled = true;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream), parts = [];
    rec.ondataavailable = (ev) => parts.push(ev.data);
    rec.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop());
      recorded = new Blob(parts, { type: rec.mimeType });
      $("rec-state").textContent = "Voice reference recorded. It will be used for this audit.";
      $("rec").disabled = false;
    };
    rec.start();
    $("rec-state").textContent = "Recording… read any sentence aloud.";
    setTimeout(() => rec.stop(), 8000);
  } catch {
    $("rec-state").textContent = "Microphone unavailable. Choose an audio file instead.";
    $("rec").disabled = false;
  }
});

$("left").addEventListener("click", async () => {
  const box = $("payload-box");
  if (!box.hidden) { box.hidden = true; return; }
  const payload = await (await fetch(`/api/audits/${auditId}/payload`)).json();
  $("payload").textContent = JSON.stringify(payload, null, 2);
  box.hidden = false;
});

// "Check before you post": one item, one answer, nothing kept. The page shows
// only what the server returns for this item; no list of past checks is
// built anywhere, on purpose (a running list across photos would be a
// fact sheet about a person).
const CHECK_CLASS = { stop: "high", look: "medium", nothing: "low" };
$("check-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("check-file").files[0];
  if (!file) return;
  $("check-result").hidden = true;
  $("check-run").disabled = true;
  try {
    const busy = await (await fetch("/api/busy")).json();
    $("check-status").textContent = busy.busy
      ? "An audit is running. Your check will start when it finishes."
      : "Checking on this device…";
    const form = new FormData();
    form.append("file", file);
    form.append("caption", $("check-caption").value);
    const res = await fetch("/api/check", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) { $("check-status").textContent = body.detail || "The check could not run. Try again."; return; }
    $("check-status").textContent = "";
    $("check-heading").textContent = body.heading;
    $("check-heading").className = `level ${CHECK_CLASS[body.result]}`;
    $("check-findings").replaceChildren(...body.findings.map((f) =>
      el("li", { class: "finding" }, el("span", {}, f.what, f.confidence === "confirmed" ? null
        : el("span", { class: "post-reference" }, f.confidence === "likely" ? "Likely" : "Not sure")))));
    $("check-advice").replaceChildren(...body.advice.map((a) => el("li", {}, a)));
    $("check-note").hidden = !body.note; $("check-note").textContent = body.note || "";
    $("check-video-note").hidden = !body.video_note; $("check-video-note").textContent = body.video_note || "";
    $("check-result").hidden = false;
  } catch {
    $("check-status").textContent = "The local app could not be reached. Check that it is running and try again.";
  } finally {
    $("check-run").disabled = false;
  }
});
$("check-again").addEventListener("click", () => {
  $("check-form").reset();
  $("check-result").hidden = true;
  $("check-status").textContent = "";
  $("check-file").focus();
});

async function forgetRun() {
  if (auditId) await fetch(`/api/audits/${auditId}`, { method: "DELETE" });
  auditId = null; recorded = null; location.hash = "";
  clearPreview();
  $("caller-block").hidden = true;
  $("caller-list").replaceChildren();
  $("pick").reset();
  $("rec-state").textContent = "";
  $("payload-box").hidden = true;
  updateExportSelection();
  show("start");
}
$("forget").addEventListener("click", forgetRun);

// Retrying also clears the failed run's URL, so a refresh cannot reopen an
// old error or leave its upload behind after another file is selected.
for (const b of document.querySelectorAll("[data-restart]")) b.addEventListener("click", forgetRun);

// A run started from the command line (--export) arrives as #audit=<id>.
const fromHash = /audit=([0-9a-f]+)/.exec(location.hash);
if (fromHash) { auditId = fromHash[1]; show("progress"); poll(); }
