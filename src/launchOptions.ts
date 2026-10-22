// Reading and changing a Steam game's launch options. Adapted from HelixSR Manager (Unlicense, PeroTuncay).

export function readLaunchOptions(appId: number): Promise<string | null> {
  return new Promise((resolve) => {
    let done = false;
    let reg: { unregister(): void } | null = null;
    const finish = (value: string | null) => {
      if (done) return;
      done = true;
      setTimeout(() => reg?.unregister(), 0); // the callback can fire before RegisterForAppDetails returns
      resolve(value);
    };
    try {
      reg = SteamClient.Apps.RegisterForAppDetails(appId, (d: { strLaunchOptions?: string }) =>
        finish(d?.strLaunchOptions ?? ""),
      );
    } catch {
      finish(null);
    }
    setTimeout(() => finish(null), 3000);
  });
}

// Every launch option the plugin writes keeps the game's --launcher-skip choice (see LAUNCHER_SKIP_GAMES)
export function writeLaunchOptions(appId: number, value: string): boolean {
  if (String(appId) in LAUNCHER_SKIP_GAMES)
    value = withLauncherSkip(value, launcherSkipOn(String(appId)));
  try {
    SteamClient.Apps.SetAppLaunchOptions(appId, value);
    return true;
  } catch {
    return false;
  }
}

const OVERRIDES = /\bWINEDLLOVERRIDES=("[^"]*"|\S*)\s*/g;

// The DLL overrides HelixSR Scaler needs for a proxy name other than dxgi.dll, e.g. WINEDLLOVERRIDES="winmm=n,b",
// put in front of whatever the game already had; an earlier WINEDLLOVERRIDES is replaced.
export function withOverrides(current: string, wanted: string): string {
  const m = /WINEDLLOVERRIDES=("[^"]*"|\S*)/.exec(wanted);
  if (!m) return current;
  const rest = current.replace(OVERRIDES, "").trim();
  if (!rest) return `${m[0]} %command%`;
  return `${m[0]} ${rest.includes("%command%") ? rest : `%command% ${rest}`}`;
}

export function withoutOverrides(current: string): string {
  const rest = current.replace(OVERRIDES, "").trim();
  if (rest === "%command%") return "";
  // "%command% -dx12" means the same to Steam as "-dx12"
  return rest.startsWith("%command% ") && !rest.slice(10).includes("%command%") ? rest.slice(10) : rest;
}

// Games that open their own launcher (REDlauncher) first: --launcher-skip, which goes straight to the game, is put in
// their launch options unless it is turned off for the game
export const LAUNCHER_SKIP_GAMES: Record<string, string> = {
  "1091500": "Cyberpunk 2077",
  "292030": "The Witcher 3: Wild Hunt",
};
const LAUNCHER_SKIP = "--launcher-skip";
const SKIP_WORD = /(^|\s)--launcher-skip(?=\s|$)/g;
const LAUNCHER_SKIP_OFF_KEY = "multifg:launcherSkipOff";

function launcherSkipOff(): string[] {
  try {
    return JSON.parse(localStorage.getItem(LAUNCHER_SKIP_OFF_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export const launcherSkipOn = (appid: string) =>
  appid in LAUNCHER_SKIP_GAMES && !launcherSkipOff().includes(appid);

export function setLauncherSkip(appid: string, on: boolean) {
  const off = launcherSkipOff().filter((a) => a !== appid);
  localStorage.setItem(LAUNCHER_SKIP_OFF_KEY, JSON.stringify(on ? off : [...off, appid]));
}

// --launcher-skip goes after %command% (at the end); without it, the rest is tidied like withoutOverrides does
export function withLauncherSkip(current: string, on: boolean): string {
  const rest = current.replace(SKIP_WORD, " ").trim();
  if (on) return rest ? `${rest} ${LAUNCHER_SKIP}` : LAUNCHER_SKIP;
  return rest === "%command%" ? "" : rest;
}

export const hasLauncherSkip = (current: string) => current.replace(SKIP_WORD, " ") !== current;

export const hasOverrides = (current: string) => /\bWINEDLLOVERRIDES=/.test(current);
