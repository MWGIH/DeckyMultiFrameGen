import { useEffect, useState } from "react";
import { ButtonItem, DropdownItem, Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  helixsrGameStatus,
  helixsrInstallGame,
  helixsrUninstallGame,
  type HelixGame,
  type HelixRoute,
  type HelixStatus,
} from "../api";
import { readLaunchOptions, withOverrides, withoutOverrides, hasOverrides, writeLaunchOptions } from "../launchOptions";

const WAYS: Record<string, string> = {
  direct: "FSR drop-in",
  scaler: "HelixSR Scaler",
  optiscaler: "OptiScaler (earlier HelixSR version)",
  dlss: "DLSS loader (earlier HelixSR version)",
  olddrop: "FSR drop-in in an OptiScaler folder (earlier HelixSR version)",
};

const IN_GAME: Record<HelixRoute, string> = {
  direct: "In the game, select AMD FSR as the upscaler.",
  scaler: "In the game, select DLSS (or FSR / XeSS if it has no DLSS). Press Insert for HelixSR Scaler's menu.",
};

function toast(body: string) {
  toaster.toast({ title: "HelixSR", body });
}

// Steam launch options HelixSR Scaler needs when it goes in under a name other than dxgi.dll.
async function syncLaunchOptions(appid: string, wanted: string | null | undefined) {
  const id = Number(appid);
  const current = await readLaunchOptions(id);
  if (current === null) {
    if (wanted) toast(`Couldn't read the launch options. Set them in Steam: ${wanted}`);
    return;
  }
  const next = wanted ? withOverrides(current, wanted) : hasOverrides(current) ? withoutOverrides(current) : current;
  if (next !== current && !writeLaunchOptions(id, next)) {
    toast(`Couldn't set the launch options. Set them in Steam: ${wanted ?? "(remove WINEDLLOVERRIDES)"}`);
  }
}

export function HelixSRGame({ appid, helix }: { appid: string; helix: HelixStatus | null }) {
  const [game, setGame] = useState<HelixGame | null>(null);
  const [route, setRoute] = useState<HelixRoute | "auto">("auto");
  const [busy, setBusy] = useState(false);
  const ready = Boolean(helix?.active_ready);

  const load = () => helixsrGameStatus(appid).then(setGame);
  useEffect(() => {
    setGame(null);
    setRoute("auto");
    if (helix?.active) load();
  }, [appid, helix?.active, ready]);

  if (!helix?.active) {
    return (
      <PanelSectionRow>
        <Field label="HelixSR" description="Install HelixSR below first." />
      </PanelSectionRow>
    );
  }
  if (!game) {
    return (
      <PanelSectionRow>
        <Field label="Checking the game for HelixSR…" />
      </PanelSectionRow>
    );
  }
  if (!game.ok) {
    return (
      <PanelSectionRow>
        <Field label="HelixSR" description={game.error} />
      </PanelSectionRow>
    );
  }
  if (!game.found) {
    return (
      <PanelSectionRow>
        <Field
          label="HelixSR can't be used here"
          description="HelixSR found no DLSS, XeSS or FSR files in this game. It only works in DirectX 12 games with one of them."
        />
      </PanelSectionRow>
    );
  }

  const ways = game.ways ?? [];
  const chosen: HelixRoute | undefined = route === "auto" ? (game.route as HelixRoute) : route;

  const install = async () => {
    setBusy(true);
    try {
      const r = await helixsrInstallGame(appid, route === "auto" ? "" : route);
      if (r.ok) {
        await syncLaunchOptions(appid, r.launch_options);
        toast(`Installed (${WAYS[r.route ?? ""] ?? r.route}). ${IN_GAME[r.route as HelixRoute] ?? ""}`);
      } else {
        toast(r.error ?? "Install failed");
      }
    } finally {
      setBusy(false);
      load();
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      const r = await helixsrUninstallGame(appid);
      if (r.ok) {
        await syncLaunchOptions(appid, null);
        toast("Removed. The game's own files are back.");
      } else {
        toast(r.error ?? "Removing failed");
      }
    } finally {
      setBusy(false);
      load();
    }
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label={game.installed ? `HelixSR installed (${WAYS[game.current ?? ""] ?? game.current})` : "HelixSR not installed"}
          description={
            game.installed && game.current && game.current in IN_GAME
              ? IN_GAME[game.current as HelixRoute]
              : game.label
          }
        />
      </PanelSectionRow>
      {(game.anticheat?.length ?? 0) > 0 && (
        <PanelSectionRow>
          <Field
            label="Anti-cheat found"
            description={`${game.anticheat!.join(", ")}: only the FSR drop-in is allowed, and changing game files can still risk an online ban.`}
          />
        </PanelSectionRow>
      )}
      {ways.length > 1 && (
        <PanelSectionRow>
          <DropdownItem
            label="Method"
            rgOptions={[
              { data: "auto", label: `Automatic (${WAYS[game.route ?? ""] ?? "-"})` },
              ...ways.map((w) => ({ data: w, label: WAYS[w] })),
            ]}
            selectedOption={route}
            onChange={(o) => setRoute(o.data)}
          />
        </PanelSectionRow>
      )}
      {ways.length > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy || !ready} onClick={install}>
            {!ready
              ? "Waiting for HelixSR's setup"
              : game.installed
                ? game.current === chosen
                  ? `Update HelixSR in this game (${helix.active})`
                  : `Switch to ${WAYS[chosen ?? ""] ?? chosen}`
                : `Install HelixSR (${WAYS[chosen ?? ""] ?? chosen})`}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {game.installed && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={remove}>
            Remove HelixSR from this game
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
