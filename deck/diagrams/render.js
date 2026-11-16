// Renders each diagrams/*.src.html to assets/*.png.
// Steps: inline Lucide icons -> Tailwind CLI builds out.css from the classes
// actually used -> headless Edge screenshots at 2x with a transparent
// background. Run: node diagrams/render.js
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const dir = __dirname;
const root = path.join(dir, "..");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
// Viewport per diagram; must match the #frame size in its HTML so nothing is
// cropped and no empty margin ends up in the PNG.
const SIZES = { pipeline: [1300, 560], post: [560, 540] };

const icon = (name) =>
  fs.readFileSync(path.join(root, "node_modules/lucide-static/icons", name + ".svg"), "utf8")
    .replace(/<!--.*?-->/s, "");

for (const [name, [w, h]] of Object.entries(SIZES)) {
  const src = fs.readFileSync(path.join(dir, name + ".src.html"), "utf8");
  fs.writeFileSync(path.join(dir, name + ".html"), src.replace(/\{\{icon:([\w-]+)\}\}/g, (_, n) => icon(n)));
}

// Tailwind scans the generated HTML (see @source in input.css).
execFileSync("npx", ["@tailwindcss/cli", "-i", path.join(dir, "input.css"), "-o", path.join(dir, "out.css")],
  { cwd: root, stdio: "inherit", shell: true });

fs.mkdirSync(path.join(root, "assets"), { recursive: true });
for (const [name, [w, h]] of Object.entries(SIZES)) {
  execFileSync(EDGE, [
    "--headless=new", "--disable-gpu", "--hide-scrollbars",
    "--default-background-color=00000000", "--force-device-scale-factor=2",
    `--window-size=${w},${h}`, `--screenshot=${path.join(root, "assets", name + ".png")}`,
    "file:///" + path.join(dir, name + ".html").replace(/\\/g, "/"),
  ], { stdio: "inherit" });
}
