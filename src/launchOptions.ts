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

export function writeLaunchOptions(appId: number, value: string): boolean {
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

export const hasOverrides = (current: string) => /\bWINEDLLOVERRIDES=/.test(current);
