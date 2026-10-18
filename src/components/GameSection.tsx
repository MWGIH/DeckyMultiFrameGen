import { useEffect, useState } from "react";
import { DropdownItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  getGame,
  setGameBackend,
  type Backend,
  type GameChoice,
  type GameDetail,
  type GameSummary,
  type HelixStatus,
  type OptiStatus,
} from "../api";
import type { SelectedGame } from "../hooks/useSelectedGame";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";
import { HelixSRGame } from "./HelixSRGame";
import { OptiScalerGame } from "./OptiScaler";

const CHOICE_LABELS: Record<GameChoice, string> = {
  none: "Off",
  optiscaler: "OptiScaler",
  helixsr: "HelixSR",
  mako: "MAKO",
};

const toast = (body: string) => toaster.toast({ title: "MultiFrameGen", body });

const SOURCE_LABELS = {
  running: "Running now",
  library: "Open in your library",
  picked: "Picked from the list",
};

// The backends a choice needs installed before it can be applied.
const NEEDS: Record<GameChoice, string[]> = {
  none: [],
  optiscaler: ["optiscaler"],
  helixsr: ["helixsr"],
  mako: ["mako"],
};

type Props = {
  selected: SelectedGame;
  games: GameSummary[];
  backends: Backend[] | null;
  helix: HelixStatus | null;
  opti: OptiStatus | null;
  onPick: (appid: string) => void;
};

// Choices whose per-game controls aren't built yet
const COMING: GameChoice[] = ["mako"];

export function GameSection({ selected, games, backends, helix, opti, onPick }: Props) {
  const [detail, setDetail] = useState<GameDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    if (selected) {
      getGame(selected.appid).then((d) => {
        if (!cancelled) setDetail(d);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [selected?.appid]);

  const [switching, setSwitching] = useState(false);
  // Switching takes the previous choice out of the game (OptiScaler and HelixSR can't both be in it)
  const choose = async (choice: GameChoice) => {
    if (!selected || choice === detail?.backend) return;
    const id = Number(selected.appid);
    setSwitching(true);
    try {
      const current = detail?.installed ? await readLaunchOptions(id) : null;
      const r = await setGameBackend(selected.appid, choice, current);
      if (r.ok) {
        setDetail((d) => (d ? { ...d, backend: choice } : d));
        if (r.launch_options != null && !writeLaunchOptions(id, r.launch_options)) {
          toast(`Couldn't update the launch options. Set them in Steam: ${r.launch_options || "(empty)"}`);
        }
        if (r.removed?.length) toast(`Removed ${r.removed.join(" and ")} from this game.`);
      } else {
        toast(r.message ?? "Couldn't save the choice");
      }
    } finally {
      setSwitching(false);
    }
  };

  const installed = new Set((backends ?? []).filter((b) => b.installed).map((b) => b.id as string));
  const missing = (choice: GameChoice) => NEEDS[choice].filter((id) => !installed.has(id));
  const name = detail?.name ?? selected?.name ?? (selected ? `App ${selected.appid}` : "");

  return (
    <PanelSection title="Game">
      <PanelSectionRow>
        <DropdownItem
          label="Choose a game"
          description="Used when no game is running and no game page is open"
          menuLabel="Installed games"
          strDefaultLabel="Pick a game"
          rgOptions={games.map((g) => ({ data: g.appid, label: g.name }))}
          selectedOption={selected?.source === "picked" ? selected.appid : undefined}
          onChange={(o) => onPick(String(o.data))}
        />
      </PanelSectionRow>
      {selected && (
        <>
          <PanelSectionRow>
            <Field label={name} description={SOURCE_LABELS[selected.source]}>
              {detail && !detail.installed ? "Not installed" : null}
            </Field>
          </PanelSectionRow>
          {detail?.ok && (
            <PanelSectionRow>
              <DropdownItem
                label="Use"
                description={
                  detail.backend && COMING.includes(detail.backend) && missing(detail.backend).length
                    ? `Needs ${missing(detail.backend).join(" and ")} installed first`
                    : detail.backend && COMING.includes(detail.backend)
                      ? "Applying this choice to the game comes in a later version"
                      : undefined
                }
                rgOptions={(detail.choices ?? []).map((c) => ({ data: c, label: CHOICE_LABELS[c] }))}
                selectedOption={detail.backend}
                disabled={switching}
                onChange={(o) => choose(o.data as GameChoice)}
              />
            </PanelSectionRow>
          )}
          {detail?.ok && detail.installed && detail.backend === "helixsr" && (
            <HelixSRGame appid={selected.appid} helix={helix} />
          )}
          {detail?.ok && detail.installed && detail.backend === "optiscaler" && (
            <OptiScalerGame appid={selected.appid} status={opti} />
          )}
        </>
      )}
    </PanelSection>
  );
}
