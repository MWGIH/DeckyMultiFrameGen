import { useEffect, useState } from "react";
import { toaster } from "@decky/api";
import { checkUpdates, type Updates } from "./api";

const LAST_KEY = "multifg:lastUpdateCheck";
const NOTIFIED_KEY = "multifg:notifiedUpdates";
const AVAILABLE_KEY = "multifg:availableUpdates"; // the last check's updates, for the line above Show backends
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

function readAvailable(): string[] {
  try {
    const list = JSON.parse(read(AVAILABLE_KEY) ?? "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

const listeners = new Set<(found: string[]) => void>();

// Every check (the daily one and Check for updates) leaves what it found here
export function rememberUpdates(u: Updates): string[] {
  const found = availableUpdates(u);
  write(AVAILABLE_KEY, JSON.stringify(found));
  listeners.forEach((l) => l(found));
  return found;
}

// What the last check found, kept up to date while the panel is open
export function useAvailableUpdates(): string[] {
  const [found, setFound] = useState(readAvailable);
  useEffect(() => {
    listeners.add(setFound);
    return () => {
      listeners.delete(setFound);
    };
  }, []);
  return found;
}

async function checkIfDue(force = false) {
  const last = Number(read(LAST_KEY) ?? 0);
  if (!force && Date.now() - last < DAY_MS) return;
  write(LAST_KEY, String(Date.now()));
  let found: string[];
  try {
    found = rememberUpdates(await checkUpdates());
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
  // a minute after Steam starts (not during its own startup), and every Steam start: the line above Show backends
  // then shows what's new, also after MultiFrameGen was updated
  const first = setTimeout(() => checkIfDue(true), 60 * 1000);
  const id = setInterval(() => checkIfDue(), TICK_MS);
  return () => {
    clearTimeout(first);
    clearInterval(id);
  };
}
