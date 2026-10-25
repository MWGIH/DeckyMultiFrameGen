import { toaster } from "@decky/api";
import { checkUpdates, type Updates } from "./api";

const LAST_KEY = "multifg:lastUpdateCheck";
const NOTIFIED_KEY = "multifg:notifiedUpdates";
const DAY_MS = 24 * 60 * 60 * 1000;
const TICK_MS = 60 * 60 * 1000; // looks every hour whether a day has passed since the last check

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // not remembered: the next check simply runs again
  }
}

// What has an update, e.g. ["MultiFrameGen 0.7.0", "HelixSR v2.0.0"]
export function availableUpdates(u: Updates): string[] {
  const out: string[] = [];
  if (u.plugin.update_available && u.plugin.latest)
    out.push(`MultiFrameGen ${u.plugin.latest}`);
  if (u.optiscaler.update_available)
    out.push(`OptiScaler ${u.optiscaler.available ?? ""}`.trim());
  if (u.helixsr.update_available)
    out.push(`HelixSR ${u.helixsr.available ?? ""}`.trim());
  if (u.mako.update_available)
    out.push(`MAKO ${u.mako.available ?? ""}`.trim());
  if (u.fsr4injector?.update_available)
    out.push(`FSR4 Injector ${u.fsr4injector.available ?? ""}`.trim());
  return out;
}

async function checkIfDue() {
  const last = Number(read(LAST_KEY) ?? 0);
  if (Date.now() - last < DAY_MS) return;
  write(LAST_KEY, String(Date.now()));
  let found: string[];
  try {
    found = availableUpdates(await checkUpdates());
  } catch {
    return; // offline: tried again tomorrow
  }
  // each set of updates is announced once, not every day until it's installed
  const key = found.join(", ");
  if (!found.length || key === read(NOTIFIED_KEY)) return;
  write(NOTIFIED_KEY, key);
  toaster.toast({
    title: "MultiFrameGen: updates available",
    body: `${key}. Open MultiFrameGen, Backends, Check for updates${found.length > 1 && found[0].startsWith("MultiFrameGen") ? ", and update MultiFrameGen first" : ""}.`,
    duration: 10000,
  });
}

// Started once when the plugin loads; returns the function that stops it
export function startDailyUpdateCheck(): () => void {
  const first = setTimeout(checkIfDue, 60 * 1000); // a minute after Steam starts, not during its own startup
  const id = setInterval(checkIfDue, TICK_MS);
  return () => {
    clearTimeout(first);
    clearInterval(id);
  };
}
