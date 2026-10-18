import { useEffect, useState } from "react";
import { DropdownItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { getGame, setGameBackend, type Backend, type GameChoice, type GameDetail, type GameSummary } from "../api";
import type { SelectedGame } from "../hooks/useSelectedGame";

const CHOICE_LABELS: Record<GameChoice, string> = {
  none: "Off",
  optiscaler: "OptiScaler",
  helixsr: "HelixSR",
  "optiscaler+helixsr": "OptiScaler with HelixSR",
  mako: "MAKO",
};

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
  "optiscaler+helixsr": ["optiscaler", "helixsr"],
  mako: ["mako"],
};

type Props = {
  selected: SelectedGame;
  games: GameSummary[];
  backends: Backend[] | null;
  onPick: (appid: string) => void;
};

export function GameSection({ selected, games, backends, onPick }: Props) {
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

  const choose = async (choice: GameChoice) => {
    if (!selected) return;
    const r = await setGameBackend(selected.appid, choice);
    if (r.ok) {
      setDetail((d) => (d ? { ...d, backend: choice } : d));
    } else {
      toaster.toast({ title: "MultiFrameGen", body: r.message ?? "Couldn't save the choice" });
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
                  detail.backend && missing(detail.backend).length
                    ? `Needs ${missing(detail.backend).join(" and ")} installed first`
                    : "Applying the choice to the game comes in the next version"
                }
                rgOptions={(detail.choices ?? []).map((c) => ({ data: c, label: CHOICE_LABELS[c] }))}
                selectedOption={detail.backend}
                onChange={(o) => choose(o.data as GameChoice)}
              />
            </PanelSectionRow>
          )}
        </>
      )}
    </PanelSection>
  );
}
