import { useEffect, useState } from "react";
import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { BelowDropdown, openPicker } from "./BelowDropdown";
import { ProgressRow } from "./ProgressRow";
import { GAME_NOTES } from "../gameNotes";
import { toaster } from "@decky/api";
import {
  getGame,
  setGameBackend,
  type Backend,
  type GameChoice,
  type GameDetail,
  type Fsr4Status,
  type AnrStatus,
  type GameSummary,
  type HelixStatus,
  type OptiStatus,
} from "../api";
import type { SelectedGame } from "../hooks/useSelectedGame";
import {
  hasLauncherSkip,
  LAUNCHER_SKIP_GAMES,
  launcherSkipOn,
  readLaunchOptions,
  setLauncherSkip,
  withLauncherSkip,
  writeLaunchOptions,
} from "../launchOptions";
import { HelixSRGame } from "./HelixSRGame";
import { OptiScalerGame } from "./OptiScaler";
import { MakoGame } from "./MakoGame";
import { HelixInOptiGame } from "./HelixInOpti";
import { Fsr4Game } from "./FSR4Injector";
import { AnrGame } from "./ANRFG";
import { useShowAll } from "../showAll";
import { GameFolder } from "./GameFolder";
import { defaultProxyDll } from "../optiscalerOptions";

const CHOICE_LABELS: Record<GameChoice, string> = {
  none: "Off",
  optiscaler: "OptiScaler",
  helixsr: "HelixSR",
  mako: "MAKO",
  "optiscaler+mako": "OptiScaler + MAKO",
  "helixsr+mako": "HelixSR + MAKO",
  "optiscaler+helixsr": "OptiScaler + HelixSR",
  "optiscaler+helixsr+mako": "OptiScaler + HelixSR + MAKO",
  fsr4injector: "FSR4 Injector (FSR 3.1+ games)",
  "fsr4injector+mako": "FSR4 Injector + MAKO (FSR 3.1+ games)",
  anrfg: "ANR FG (DLSS frame generation games)",
};

// The Use list's order (Martin's pick): Off, ANR FG, FSR4 Injector, then combined options, single methods last
const CHOICE_ORDER: GameChoice[] = [
  "none",
  "anrfg",
  "fsr4injector",
  "helixsr+mako",
  "optiscaler+helixsr+mako",
  "optiscaler+helixsr",
  "optiscaler+mako",
  "fsr4injector+mako",
  "helixsr",
  "optiscaler",
  "mako",
];
const choiceRank = (c: GameChoice) => {
  const i = CHOICE_ORDER.indexOf(c);
  return i < 0 ? CHOICE_ORDER.length : i;
};

// One line above Use on what the game is set up with, split into upscaler and frame generation
const SETUP: Record<GameChoice, [string, string]> = {
  none: ["", ""],
  optiscaler: ["OptiScaler", "OptiScaler"],
  helixsr: ["HelixSR", "none"],
  mako: ["game's own", "MAKO"],
  "optiscaler+mako": ["OptiScaler", "MAKO"],
  "helixsr+mako": ["HelixSR", "MAKO"],
  "optiscaler+helixsr": ["HelixSR in OptiScaler", "OptiScaler"],
  "optiscaler+helixsr+mako": ["HelixSR in OptiScaler", "MAKO"],
  fsr4injector: ["FSR 4 (FSR4 Injector)", "game's own"],
  "fsr4injector+mako": ["FSR 4 (FSR4 Injector)", "MAKO"],
  anrfg: ["game's own", "ANR FG"],
};

function setupSummary(choice: GameChoice, running: boolean): string {
  const [up, fg] = SETUP[choice] ?? ["", ""];
  const line =
    choice === "none"
      ? "Currently set: Off"
      : `Currently set: ${up} upscaler, ${fg === "none" ? "no" : fg} frame gen`;
  return running ? `${line} · Running` : line;
}

const parts = (choice: GameChoice | null | undefined) =>
  choice ? choice.split("+") : [];

const toast = (body: string) => toaster.toast({ title: "MultiFrameGen", body });

// Under Use: what the game ships, and which choices that leaves out
function useDescription(detail: GameDetail, showAll: boolean): string | undefined {
  if (detail.upscalers == null) return undefined;
  const found = detail.upscalers.length
    ? `Found in the game: ${detail.upscalers.join(", ")}.`
    : "No FSR, DLSS or XeSS files found in the game.";
  const hidden = (detail.hidden ?? []).filter((h) => !h.choice.endsWith("+mako"));
  if (showAll) return `${found} Showing all options (Debug).`;
  if (!hidden.length) return found;
  const left = hidden
    .map(
      (h) =>
        `${CHOICE_LABELS[h.choice].replace(/ \(.*\)$/, "")} (${h.reason ?? `needs ${h.needs.join(" or ")}`})`,
    )
    .join(", ");
  return `${found} Not offered: ${left}.`;
}

const SOURCE_LABELS = {
  running: "Running now",
  library: "Open in your library",
  picked: "Picked from the list",
};

type Props = {
  selected: SelectedGame;
  games: GameSummary[];
  backends: Backend[] | null;
  helix: HelixStatus | null;
  opti: OptiStatus | null;
  fsr4: Fsr4Status | null;
  anr: AnrStatus | null;
  onPick: (appid: string) => void;
  onChoice: (choice: GameChoice | null) => void;
};

export function GameSection({
  selected,
  games,
  backends,
  helix,
  opti,
  fsr4,
  anr,
  onPick,
  onChoice,
}: Props) {
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [reload, setReload] = useState(0); // bumped after a non-Steam game's folder changes

  useEffect(() => {
    setDetail(null);
    setReload(0);
  }, [selected?.appid]);
  useEffect(() => {
    let cancelled = false;
    if (selected) {
      getGame(selected.appid).then((d) => {
        if (!cancelled) setDetail(d);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [selected?.appid, reload]);
  useEffect(
    () =>
      onChoice(
        detail?.ok && detail.installed ? (detail.backend ?? null) : null,
      ),
    [detail],
  );

  // --launcher-skip in the launch options of games with their own launcher, as soon as the game is shown
  const [skipLauncher, setSkipLauncher] = useState(false);
  const skipGame = Boolean(selected && selected.appid in LAUNCHER_SKIP_GAMES);
  useEffect(() => {
    if (!selected || !skipGame || !detail?.ok || !detail.installed) return;
    const id = Number(selected.appid);
    const on = launcherSkipOn(selected.appid);
    setSkipLauncher(on);
    readLaunchOptions(id).then((current) => {
      if (current !== null && hasLauncherSkip(current) !== on)
        writeLaunchOptions(id, withLauncherSkip(current, on));
    });
  }, [selected?.appid, detail?.ok, detail?.installed]);
  const toggleSkipLauncher = async (on: boolean) => {
    if (!selected) return;
    const id = Number(selected.appid);
    setLauncherSkip(selected.appid, on);
    setSkipLauncher(on);
    const current = await readLaunchOptions(id);
    if (current === null || !writeLaunchOptions(id, withLauncherSkip(current, on)))
      toast(
        `Couldn't change the launch options. ${on ? "Add" : "Remove"} --launcher-skip in Steam.`,
      );
  };

  const [showAll] = useShowAll();
  // The choice being patched in (or "none" while a method is taken out); null when nothing is running
  const [switching, setSwitching] = useState<GameChoice | null>(null);
  // Switching swaps DLLs and launch options the running game already loaded, so it waits until the game is closed
  const gameRunning = selected?.source === "running";
  const [optiChanged, setOptiChanged] = useState(0);
  // the game whose OptiScaler patch just failed on choosing Use, so its panel doesn't patch it again by itself
  const [optiFailed, setOptiFailed] = useState<string | null>(null);
  // Switching takes the previous choice out of the game (OptiScaler and HelixSR can't both be in it)
  const choose = async (choice: GameChoice) => {
    if (!selected || choice === detail?.backend) return;
    if (gameRunning) {
      toast("Close the game before changing Use.");
      return;
    }
    const id = Number(selected.appid);
    const gameName = detail?.name ?? selected.name ?? "the game";
    setSwitching(choice);
    setOptiFailed(null);
    // One toast per change, once it's done: the panel shows the progress meanwhile
    try {
      const current = detail?.installed ? await readLaunchOptions(id) : null;
      const r = await setGameBackend(
        selected.appid,
        choice,
        current,
        defaultProxyDll(selected.appid),
      );
      if (r.ok) {
        if (r.opti && !r.opti.ok) setOptiFailed(selected.appid);
        setDetail((d) => (d ? { ...d, backend: choice } : d));
        const problems: string[] = [];
        const hints: string[] = [];
        if (
          r.launch_options != null &&
          !writeLaunchOptions(id, r.launch_options)
        )
          problems.push(
            `Couldn't update the launch options. Set them in Steam: ${r.launch_options || "(empty)"}`,
          );
        if (r.opti) {
          if (r.opti.ok) hints.push("Select DLSS in the game to get FSR / XeSS; Insert opens OptiScaler's menu.");
          else problems.push(`OptiScaler wasn't patched in: ${r.opti.error}`);
        }
        if (r.fsr4) {
          if (r.fsr4.ok) hints.push("Choose AMD FSR as the game's upscaler.");
          else problems.push(`FSR4 Injector wasn't put in: ${r.fsr4.error}`);
        }
        if (r.anr) {
          if (r.anr.ok) hints.push("Turn on DLSS frame generation in the game.");
          else problems.push(`ANR FG wasn't put in: ${r.anr.error}`);
        }
        if (r.helix) {
          if (!r.helix.ok) problems.push(`HelixSR wasn't put in: ${r.helix.error}`);
          else if (r.helix.route === "scaler")
            hints.push("Select DLSS in the game (or FSR / XeSS without DLSS); Insert opens HelixSR's menu.");
          else hints.push("Select AMD FSR as the game's upscaler.");
        }
        if (r.helix_in_opti && !r.helix_in_opti.ok)
          problems.push(`HelixSR wasn't added to OptiScaler: ${r.helix_in_opti.error}`);
        setOptiChanged((n) => n + 1);
        const what =
          choice === "none"
            ? `${CHOICE_LABELS[detail?.backend ?? "none"].replace(/ \(.*\)$/, "")} removed from ${gameName}.`
            : `${gameName} is set to ${CHOICE_LABELS[choice].replace(/ \(.*\)$/, "")}.`;
        toast(
          problems.length
            ? `${what} ${problems.join(" ")}`
            : `${what} You can start the game now.${hints.length ? " " + hints.join(" ") : ""}`,
        );
      } else {
        toast(r.message ?? "Couldn't save the choice");
      }
    } finally {
      setSwitching(null);
    }
  };

  const installed = new Set(
    (backends ?? []).filter((b) => b.installed).map((b) => b.id as string),
  );
  const name =
    detail?.name ?? selected?.name ?? (selected ? `App ${selected.appid}` : "");

  return (
    <PanelSection title="Game">
      {(!selected || selected.source === "picked") && (
        <PanelSectionRow>
          <BelowDropdown
            label="Choose a game"
            description="No game is running or open in your library"
            menuLabel="Installed games"
            strDefaultLabel="Pick a game"
            rgOptions={games.map((g) => ({
              data: g.appid,
              label: g.non_steam ? `${g.name} (non-Steam)` : g.name,
            }))}
            selectedOption={
              selected?.source === "picked" ? selected.appid : undefined
            }
            onChange={(o) => onPick(String(o.data))}
          />
        </PanelSectionRow>
      )}
      {selected && (
        <>
          <PanelSectionRow>
            <Field
              label={name}
              description={`${SOURCE_LABELS[selected.source]}${detail?.non_steam ? " · Non-Steam game" : ""}`}
            >
              {detail && !detail.installed ? (detail.non_steam ? "Folder needed" : "Not installed") : null}
            </Field>
          </PanelSectionRow>
          {detail?.ok && detail.non_steam && (
            <GameFolder
              appid={selected.appid}
              detail={detail}
              locked={gameRunning || switching !== null}
              onChanged={() => setReload((n) => n + 1)}
            />
          )}
          {detail?.ok && (GAME_NOTES[selected.appid] ?? GAME_NOTES[detail.notes_key ?? ""]) && (
            <PanelSectionRow>
              <Field
                label="Tested with this game"
                description={GAME_NOTES[selected.appid] ?? GAME_NOTES[detail.notes_key ?? ""]}
              />
            </PanelSectionRow>
          )}
          {detail?.ok && detail.installed && skipGame && (
            <PanelSectionRow>
              <ToggleField
                label="Skip the game's launcher"
                description="Adds --launcher-skip to the launch options so the game starts straight away. Turn it off if you need the launcher, e.g. to change its settings or mods."
                checked={skipLauncher}
                onChange={toggleSkipLauncher}
              />
            </PanelSectionRow>
          )}
          {detail?.ok && (detail.installed || !detail.non_steam || detail.backend !== "none") && (
            <PanelSectionRow>
              <Field
                label={switching !== null ? "Changing the setup…" : setupSummary(detail.backend ?? "none", gameRunning)}
                bottomSeparator="none"
              />
            </PanelSectionRow>
          )}
          {detail?.ok && gameRunning && (
            <PanelSectionRow>
              <Field
                label="⚠️ Close the game to change the option"
                description="Changing it while the game runs swaps files the game has open and can crash it, and new launch options only apply on the next start. Exit the game, then pick again."
              />
            </PanelSectionRow>
          )}
          {detail?.ok && (detail.installed || !detail.non_steam || detail.backend !== "none") && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                description={useDescription(detail, showAll)}
                disabled={switching !== null || gameRunning}
                onClick={() =>
                  openPicker(
                    "Use",
                    ((showAll ? detail.all_choices : null) ?? detail.choices ?? [])
                      // only methods that are installed, plus whatever the game is set to now
                      .filter(
                        (c) =>
                          c === "none" ||
                          c === detail.backend ||
                          parts(c).every((id) => installed.has(id)),
                      )
                      .slice()
                      .sort((a, b) => choiceRank(a) - choiceRank(b))
                      .map((c) => ({ data: c, label: CHOICE_LABELS[c] })),
                    detail.backend,
                    (o) => choose(o.data as GameChoice),
                  )
                }
              >
                {(detail.backend ?? "none") === "none" ? "Choose an option" : "Change option"}
              </ButtonItem>
            </PanelSectionRow>
          )}
          {switching !== null && (
            <ProgressRow
              title={
                switching === "none"
                  ? "Removing from the game, please wait…"
                  : `Patching ${CHOICE_LABELS[switching].replace(/ \(.*\)$/, "")}, please wait…`
              }
              detail="Don't start the game until this is done."
            />
          )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("helixsr") &&
            !parts(detail.backend).includes("optiscaler") && (
              <HelixSRGame appid={selected.appid} helix={helix} />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("optiscaler") && (
              <OptiScalerGame
                appid={selected.appid}
                status={opti}
                running={gameRunning}
                autoPatch={switching === null && optiFailed !== selected.appid}
                refresh={optiChanged}
                onChange={() => setOptiChanged((n) => n + 1)}
              />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("optiscaler") &&
            parts(detail.backend).includes("helixsr") && (
              <HelixInOptiGame
                appid={selected.appid}
                helix={helix}
                refresh={optiChanged}
              />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("fsr4injector") && (
              <Fsr4Game
                key={`${selected.appid}:${detail.backend}`}
                appid={selected.appid}
                status={fsr4}
              />
            )}
          {detail?.ok && detail.installed && detail.backend === "anrfg" && (
            <AnrGame key={selected.appid} appid={selected.appid} status={anr} />
          )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("mako") && (
              <MakoGame
                appid={selected.appid}
                makoInstalled={installed.has("mako")}
              />
            )}
        </>
      )}
    </PanelSection>
  );
}
