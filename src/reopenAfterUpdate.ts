import { Navigation, QuickAccessTab } from "@decky/ui";

// Decky keeps showing the panel of the copy that was open when the plugin reloads (its active plugin is the old
// copy's object), so after an update the panel shows the old version's state until it is closed and opened again.
// The new copy fixes that itself when it loads; after an update started from the panel it also closes the Quick
// Access Menu and opens it again on this plugin.

export const PLUGIN_NAME = "Decky MultiFrameGen"; // plugin.json's name
const FLAG = "multifg:reopenAfterUpdate";
const FLAG_MAX_AGE_MS = 10 * 60 * 1000; // the update was cancelled or failed if the new copy hasn't loaded by then

type DeckyState = {
  publicState(): { plugins: { name: string }[]; activePlugin: { name: string } | null };
  setActivePlugin(name: string): void;
};

function deckyState(): DeckyState | null {
  const loader = (window as unknown as { DeckyPluginLoader?: { deckyState?: DeckyState } }).DeckyPluginLoader;
  return loader?.deckyState ?? null;
}

// called before Decky's installer replaces this copy
export function markUpdating() {
  try {
    localStorage.setItem(FLAG, String(Date.now()));
  } catch {
    // the panel just isn't reopened
  }
}

function takeFlag(): boolean {
  try {
    const at = Number(localStorage.getItem(FLAG));
    localStorage.removeItem(FLAG);
    return !!at && Date.now() - at < FLAG_MAX_AGE_MS;
  } catch {
    return false;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function reopenAfterUpdate() {
  const updated = takeFlag();
  const state = deckyState();
  if (!state) return;
  // Decky adds this copy to its list just after loading it
  let mine: { name: string } | undefined;
  for (let i = 0; i < 50 && !mine; i++) {
    await sleep(200);
    mine = state.publicState().plugins.find((p) => p.name === PLUGIN_NAME);
  }
  if (!mine) return;
  const active = state.publicState().activePlugin;
  const stale = active?.name === PLUGIN_NAME && active !== mine;
  if (updated) {
    Navigation.CloseSideMenus();
    await sleep(400);
    state.setActivePlugin(PLUGIN_NAME);
    Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
  } else if (stale) {
    state.setActivePlugin(PLUGIN_NAME);
  }
}
