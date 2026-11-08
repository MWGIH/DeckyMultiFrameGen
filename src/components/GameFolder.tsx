import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import type { FileSelectionType } from "@decky/api/dist/types";
import { useState } from "react";
import { setGameFolder, type GameDetail } from "../api";

const FOLDER = 1 as FileSelectionType; // FileSelectionType.FOLDER (a const enum, so not in the bundle)

const SOURCES: Record<string, string> = {
  shortcut: "Found from the shortcut",
  heroic: "Found in Heroic",
  lutris: "Found in Lutris",
  picked: "Chosen by you",
};

const toast = (body: string) => toaster.toast({ title: "MultiFrameGen", body });

type Props = {
  appid: string;
  detail: GameDetail;
  locked: boolean; // the game is running
  onChanged: () => void;
};

// A non-Steam game's folder: found from its shortcut (or Heroic / Lutris), or chosen here when the shortcut starts a
// launcher (EA app, Battle.net, ...) or the guess is wrong
export function GameFolder({ appid, detail, locked, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const inUse = (detail.backend ?? "none") !== "none";
  const via = detail.launcher;

  const save = async (folder: string) => {
    setBusy(true);
    try {
      const r = await setGameFolder(appid, folder);
      if (!r.ok) toast(r.error ?? "Couldn't save the folder");
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const choose = async () => {
    let picked: string;
    try {
      const r = await openFilePicker(FOLDER, detail.install_path || detail.browse_start || "/home/deck", false, true);
      picked = r.realpath || r.path;
    } catch {
      return; // cancelled
    }
    if (picked) await save(picked);
  };

  const description = detail.installed
    ? `${detail.install_path}${detail.folder_source ? ` (${SOURCES[detail.folder_source] ?? ""})` : ""}`
    : via
      ? `This shortcut starts ${via}, so the game's folder isn't known. Choose the folder with the game's .exe.`
      : "The game's folder wasn't found from its shortcut. Choose the folder with the game's .exe.";

  return (
    <>
      <PanelSectionRow>
        <Field label="Game folder" description={description} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy || inUse || locked}
          description={inUse ? "Set Use to Off to change the folder." : undefined}
          onClick={choose}
        >
          {detail.installed ? "Change game folder" : "Choose game folder"}
        </ButtonItem>
      </PanelSectionRow>
      {detail.folder_source === "picked" && !inUse && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy || locked} onClick={() => save("")}>
            Use the folder found from the shortcut
          </ButtonItem>
        </PanelSectionRow>
      )}
      {detail.installed && via && (
        <PanelSectionRow>
          <Field
            label={`Starts through ${via}`}
            description={
              via === "Heroic" || via === "Lutris" || via === "Bottles" || via === "Legendary"
                ? `The launch options set here have to reach the game through ${via}. If a method doesn't load, add the same WINEDLLOVERRIDES (shown in Steam's launch options) to the game's environment variables in ${via}.`
                : `One Use choice per shortcut: it applies to the game in the folder above. Set Use to Off before switching the folder to another game ${via} starts.`
            }
          />
        </PanelSectionRow>
      )}
    </>
  );
}
