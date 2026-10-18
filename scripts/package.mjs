// Builds out/Decky-MultiFrameGen.zip in the layout Decky's "Install plugin from ZIP" expects:
// one top folder with plugin.json, package.json, main.py, py_modules/, assets/, dist/index.js and the licenses.
// Adapted from HelixSR Manager's package script (Unlicense, PeroTuncay).
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync } from "node:fs";

const name = "Decky-MultiFrameGen";

// Decky runs main.py on its own bundled Python, older than 3.12: syntax only newer Pythons accept makes the
// backend fail to load. Compile the backend with an older interpreter if one is around.
const oldPythons = ["python3.11", "python3.10", "python3.9", "/usr/bin/python3"];
let checked = false;
for (const py of oldPythons) {
  let version;
  try {
    version = execFileSync(py, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"], { encoding: "utf8" }).trim();
  } catch {
    continue;
  }
  const [major, minor] = version.split(".").map(Number);
  if (major !== 3 || minor >= 12) continue;
  try {
    execFileSync(py, ["-m", "compileall", "-q", "main.py", "py_modules"], { stdio: "pipe" });
  } catch (e) {
    console.error(`The backend doesn't compile on Python ${version} (Decky's Python is older than 3.12):`);
    console.error(String(e.stdout) + String(e.stderr));
    process.exit(1);
  }
  console.log(`Backend compiles on Python ${version}`);
  checked = true;
  break;
}
if (!checked) console.warn("warning: no Python older than 3.12 found, the backend's compatibility with Decky wasn't checked");

rmSync("out", { recursive: true, force: true });
mkdirSync(`out/${name}/dist`, { recursive: true });
for (const f of ["plugin.json", "package.json", "main.py", "LICENSE", "README.md", "CREDITS.md"]) cpSync(f, `out/${name}/${f}`);
cpSync("dist/index.js", `out/${name}/dist/index.js`);
cpSync("py_modules", `out/${name}/py_modules`, {
  recursive: true,
  filter: (src) => !src.includes("__pycache__"),
});
cpSync("licenses", `out/${name}/licenses`, { recursive: true });
cpSync("assets", `out/${name}/assets`, { recursive: true });
cpSync("bin", `out/${name}/bin`, { recursive: true }); // MAKO's diagnostics helper, where its installer looks
execFileSync("zip", ["-qr", `${name}.zip`, name], { cwd: "out", stdio: "inherit" });
console.log(`out/${name}.zip`);
