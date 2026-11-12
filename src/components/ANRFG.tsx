import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  PanelSectionRow,
  showModal,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { BelowDropdown } from "./BelowDropdown";
import { ProgressRow } from "./ProgressRow";
import {
  anrGameOff,
  anrGameOn,
  anrGames,
  anrGameStatus,
  anrInstall,
  anrModelSize,
  anrRemove,
  anrStatus,
  type AnrGame as AnrGameStatus,
  type AnrStatus,
} from "../api";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

const POLL_RUNNING_MS = 1000;
const POLL_IDLE_MS = 10000;
const MB = 1024 * 1024;

function toast(body: string) {
  toaster.toast({ title: "ANR FG", body });
}

export function useAnrStatus() {
  const [status, setStatus] = useState<AnrStatus | null>(null);
  const running = status?.job?.state === "running";
  const wasRunning = useRef(false);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      anrStatus()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    load();
    const id = setInterval(load, running ? POLL_RUNNING_MS : POLL_IDLE_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [running]);
  useEffect(() => {
    const job = status?.job;
    if (wasRunning.current && job && job.state !== "running")
      toast(
        job.state === "done"
          ? `ANR FG ${job.version ?? ""} is ready.${job.refreshed ? ` Updated in ${job.refreshed} game(s).` : " Set a game to it under Use."}`
          : (job.error ?? "Install failed"),
      );
    wasRunning.current = running;
  }, [status?.job?.state]);
  return [status, setStatus] as const;
}

function applyLaunchOptions(
  appid: string,
  current: string,
  next: string | null | undefined,
): boolean {
  if (next == null || next === current) return true;
  if (writeLaunchOptions(Number(appid), next)) return true;
  toast(`Couldn't set the launch options. Set them in Steam: ${next || "(empty)"}`);
  return false;
}

// Takes ANR FG out of every game it is in, launch options included; returns how many couldn't be changed
async function anrOffEverywhere(): Promise<number> {
  let failed = 0;
  for (const appid of await anrGames()) {
    const current = await readLaunchOptions(Number(appid));
    const r = await anrGameOff(appid, current ?? "");
    if (!r.ok || current === null || !applyLaunchOptions(appid, current, r.launch_options))
      failed++;
  }
  return failed;
}

// In Backends: ANR FG's full package (with Apex's OptiScaler build) from its GitHub releases
export function AnrSetup({
  status,
  onChange,
}: {
  status: AnrStatus | null;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  if (!status) return null;

  const job = status.job;
  if (job?.state === "running") {
    const progress = job.total ? Math.min(1, job.done / job.total) : undefined;
    return (
      <ProgressRow
        title="Installing ANR FG"
        percent={progress === undefined ? undefined : progress * 100}
        detail={`Downloading ANR FG ${job.version ?? ""} from GitHub (${Math.round(job.done / MB)}${job.total ? ` of ${Math.round(job.total / MB)}` : ""} MB)`}
      />
    );
  }

  const install = async () => {
    setBusy(true);
    try {
      const r = await anrInstall();
      if (!r.ok) toast(r.error ?? "Install failed");
    } finally {
      setBusy(false);
      onChange();
    }
  };
  const askInstall = () =>
    showModal(
      <ConfirmModal
        strTitle="Install ANR FG"
        strDescription="Downloads ANR FG (Apex Neural Rendering, a closed-source beta) from its GitHub releases: about 11 MB. It comes with Apex's own OptiScaler build, so a game set to ANR FG doesn't use the OptiScaler from Decky Framegen. It only runs in DirectX 12 games that offer DLSS frame generation."
        strOKButtonText="Install"
        onOK={install}
      />,
    );
  const remove = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove ANR FG"
        strDescription="Takes ANR FG out of every game it is in (their own files and launch options go back), then deletes its files. Games set to it keep that choice until you change Use."
        strOKButtonText="Remove"
        onOK={async () => {
          setBusy(true);
          try {
            const failed = await anrOffEverywhere();
            const r = await anrRemove();
            toast(
              !r.ok
                ? (r.error ?? "Removing failed")
                : failed
                  ? `Removed. ${failed} game(s) still have WINEDLLOVERRIDES in their launch options: remove it in Steam.`
                  : "Removed, and taken out of your games.",
            );
          } finally {
            setBusy(false);
            onChange();
          }
        }}
      />,
    );

  return (
    <>
      {job?.state === "failed" && (
        <PanelSectionRow>
          <Field label="ANR FG install failed" description={job.error ?? undefined} />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        {status.ready ? (
          <ButtonItem layout="below" disabled={busy} onClick={remove}>
            Remove ANR FG
          </ButtonItem>
        ) : (
          <ButtonItem layout="below" disabled={busy} onClick={askInstall}>
            Install ANR FG
          </ButtonItem>
        )}
      </PanelSectionRow>
    </>
  );
}

const MODEL_SIZES = [
  { data: "auto", label: "Auto (picked for the GPU)" },
  { data: "large", label: "Large (better image)" },
  { data: "small", label: "Small (faster)" },
];

// Under Use, for a game set to ANR FG
export function AnrGame({ appid, status }: { appid: string; status: AnrStatus | null }) {
  const [game, setGame] = useState<AnrGameStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => anrGameStatus(appid).then(setGame, () => undefined);
  useEffect(() => {
    load();
  }, [appid, status?.version, status?.games.join(",")]);

  const putIn = async () => {
    setBusy(true);
    try {
      const current = (await readLaunchOptions(Number(appid))) ?? "";
      const r = await anrGameOn(appid, current);
      if (!r.ok) toast(r.error ?? "Couldn't put ANR FG in");
      else if (applyLaunchOptions(appid, current, r.launch_options))
        toast("ANR FG is in. In the game, turn on DLSS frame generation.");
    } finally {
      setBusy(false);
      load();
    }
  };
  const setSize = async (size: string) => {
    const r = await anrModelSize(appid, size);
    if (!r.ok) toast(r.error ?? "Couldn't change it");
    load();
  };

  if (!game) return null;
  return (
    <>
      {!game.ok ? (
        <PanelSectionRow>
          <Field label="ANR FG" description={game.error} />
        </PanelSectionRow>
      ) : !game.ready ? (
        <PanelSectionRow>
          <Field label="ANR FG isn't installed" description="Install it under Backends." />
        </PanelSectionRow>
      ) : game.enabled ? (
        <>
          <PanelSectionRow>
            <Field
              label="ANR FG is in the game"
              description={`In the game, turn on DLSS frame generation (pick the NVIDIA one where there are several): ANR FG runs instead. Insert opens OptiScaler's menu.\nFolder: ${game.target_dir}\nLaunch options: ${game.launch_option}`}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <BelowDropdown
              label="Model size"
              description="Small costs less GPU time per generated frame, which matters on the Steam Deck. Restart the game after a change."
              rgOptions={MODEL_SIZES}
              selectedOption={game.model_size ?? "large"}
              onChange={(o) => setSize(String(o.data))}
            />
          </PanelSectionRow>
          {game.log && (
            <PanelSectionRow>
              <Field label="Newest ANR FG log" description={game.log} />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={putIn}>
              Put ANR FG in again
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={putIn}>
            Put ANR FG in this game
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
