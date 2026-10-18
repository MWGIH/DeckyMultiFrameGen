import { useEffect, useState } from "react";
import { ButtonItem, ConfirmModal, DropdownItem, Field, PanelSectionRow, showModal } from "@decky/ui";
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
async function syncLaunchOptions(appid: string, wanted: string | null | undefined, base?: string | null) {
  const id = Number(appid);
  const current = base ?? (await readLaunchOptions(id));
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

  const eac = (game.anticheat ?? []).some((a) => /easy\s*anti-?cheat/i.test(a));
  const EAC_WARNING =
    "Easy Anti-Cheat checks the game's FSR file and stops the game when HelixSR has replaced it: you get the anti-cheat splash, then a black screen (seen in Gears of War: E-Day). Choose OptiScaler + HelixSR for this game instead: it leaves the game's files alone, and OptiScaler ran fine in Gears of War: E-Day.";

  const askInstall = () => {
    if (!eac || game.installed) {
      install();
      return;
    }
    showModal(
      <ConfirmModal
        strTitle="This game uses Easy Anti-Cheat"
        strDescription={`${EAC_WARNING} Install HelixSR anyway?`}
        strOKButtonText="Install anyway"
        onOK={install}
      />,
    );
  };

  const install = async () => {
    setBusy(true);
    try {
      const current = (await readLaunchOptions(Number(appid))) ?? "";
      const r = await helixsrInstallGame(appid, route === "auto" ? "" : route, current);
      if (r.ok) {
        // OptiScaler was taken out first: its launch options go back to what the game had before
        if (r.base_launch_options != null) writeLaunchOptions(Number(appid), r.base_launch_options);
        await syncLaunchOptions(appid, r.launch_options, r.base_launch_options);
        const removed = r.removed?.length ? `Removed ${r.removed.join(" and ")}. ` : "";
        toast(`${removed}Installed (${WAYS[r.route ?? ""] ?? r.route}). ${IN_GAME[r.route as HelixRoute] ?? ""}`);
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
      {game.installed && (
        <PanelSectionRow>
          <Field
            label={game.runtime_log ? "HelixSR's log from the game" : "HelixSR hasn't run in this game yet"}
            description={
              game.runtime_log ? (
                <div style={{ fontFamily: "monospace", fontSize: "11px", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {`${new Date(game.runtime_log.modified * 1000).toLocaleString()}\n${game.runtime_log.lines.join("\n")}`}
                </div>
              ) : (
                "HelixSR writes a log when the game loads it. If there is none after playing with the right upscaler selected, the game didn't load HelixSR."
              )
            }
          />
        </PanelSectionRow>
      )}
      {game.graphics === "vulkan" && (
        <PanelSectionRow>
          <Field
            label="This game runs on Vulkan"
            description="HelixSR only works in DirectX 12 games, so it will most likely have no effect here even though the game ships an FSR file it can replace."
          />
        </PanelSectionRow>
      )}
      {eac && (
        <PanelSectionRow>
          <Field label="HelixSR won't work with Easy Anti-Cheat" description={EAC_WARNING} />
        </PanelSectionRow>
      )}
      {!eac && (game.anticheat?.length ?? 0) > 0 && (
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
          <ButtonItem layout="below" disabled={busy || !ready} onClick={askInstall}>
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
