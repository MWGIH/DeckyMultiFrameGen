import { useEffect, useRef, useState } from "react";
import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  checkUpdates,
  helixsrInstall,
  optiscalerInstall,
  type Updates,
} from "../api";
import { installMako } from "../mako/api/makoApi";
import { availableUpdates } from "../dailyUpdateCheck";

const PLUGIN_NAME = "Decky MultiFrameGen"; // plugin.json's name: Decky replaces the installed copy with that name
const INSTALL_URL =
  "https://github.com/MWGIH/DeckyMultiFrameGen/releases/latest/download/Decky-MultiFrameGen.zip";

const toast = (body: string) => toaster.toast({ title: "Updates", body });

// Decky's own "install from URL" (it asks for confirmation, then replaces this plugin and reloads it)
async function updatePlugin(
  url: string,
  version: string,
  sha256: string | null | undefined,
) {
  const backend = (
    window as unknown as {
      DeckyBackend?: { call: (...args: unknown[]) => Promise<unknown> };
    }
  ).DeckyBackend;
  if (!backend) throw new Error("Decky's installer isn't reachable");
  await backend.call(
    "utilities/install_plugin",
    url,
    PLUGIN_NAME,
    version,
    sha256 ?? false,
    2 /* InstallType.UPDATE */,
  );
}

type Props = {
  // the backends' install jobs: an update runs in the background, so the list is checked again when it ends
  optiJobState?: string | null;
  helixJobState?: string | null;
  onOptiChange: () => void;
  onHelixChange: () => void;
  onMakoChange: () => void;
};

export function UpdatesCheck({
  optiJobState,
  helixJobState,
  onOptiChange,
  onHelixChange,
  onMakoChange,
}: Props) {
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [u, setU] = useState<Updates | null>(null);

  const check = async () => {
    setChecking(true);
    try {
      const r = await checkUpdates();
      setU(r);
      try {
        localStorage.setItem("multifg:lastUpdateCheck", String(Date.now()));
        localStorage.setItem(
          "multifg:notifiedUpdates",
          availableUpdates(r).join(", "),
        );
      } catch {
        // the daily check just runs as usual
      }
    } catch (e) {
      toast(`Couldn't check: ${e}`);
    } finally {
      setChecking(false);
    }
  };

  // an update that ran in the background has finished: its notice goes once the list is checked again
  const jobs = `${optiJobState ?? ""}/${helixJobState ?? ""}`;
  const lastJobs = useRef(jobs);
  useEffect(() => {
    const wasRunning = lastJobs.current.includes("running");
    lastJobs.current = jobs;
    if (u && wasRunning && !jobs.includes("running")) check();
  }, [jobs]);

  const run = async (
    work: () => Promise<{
      ok?: boolean;
      success?: boolean;
      status?: string;
      error?: string | null;
      message?: string | null;
    }>,
    done: string,
    after: () => void,
  ) => {
    setBusy(true);
    try {
      const r = await work();
      const ok = r.ok ?? r.success ?? r.status !== "error";
      toast(ok ? done : r.error || r.message || "Update failed");
    } finally {
      setBusy(false);
      after();
      check();
    }
  };

  const rows: JSX.Element[] = [];
  if (u) {
    const p = u.plugin;
    // a newer MultiFrameGen goes first: it can change how the backends are installed or updated
    const pluginFirst = !!(p.update_available && p.url && p.latest);
    const FIRST = " Update MultiFrameGen first, then check again.";
    if (p.error)
      rows.push(
        <Field
          key="pe"
          label="MultiFrameGen"
          description={`Couldn't check: ${p.error}`}
        />,
      );
    else if (p.update_available && p.url && p.latest) {
      rows.push(
        <Field
          key="p"
          label={`MultiFrameGen ${p.latest} is available`}
          description={`You have ${p.current}. Its update also brings newer OptiScaler and MAKO files when upstream has them.`}
        />,
      );
      rows.push(
        <ButtonItem
          key="pb"
          layout="below"
          disabled={busy}
          onClick={() =>
            updatePlugin(p.url!, p.latest!, p.sha256)
              // Decky reloads the plugin with the new version; this copy's notice goes meanwhile
              .then(() =>
                setU({ ...u, plugin: { ...p, update_available: false } }),
              )
              .catch(() =>
                toast(
                  `Couldn't start the update. Install it from Decky's settings with this URL: ${INSTALL_URL}`,
                ),
              )
          }
        >
          Update MultiFrameGen
        </ButtonItem>,
      );
    }
    const o = u.optiscaler;
    if (o.error)
      rows.push(
        <Field
          key="oe"
          label="OptiScaler"
          description={`Couldn't check: ${o.error}`}
        />,
      );
    else if (o.update_available) {
      rows.push(
        <Field
          key="o"
          label={`OptiScaler ${o.available} is available`}
          description={`You have ${o.installed}. Repatch your games afterwards: each game keeps its own copy.${pluginFirst ? FIRST : ""}`}
        />,
      );
      rows.push(
        <ButtonItem
          key="ob"
          layout="below"
          disabled={busy || pluginFirst}
          onClick={() =>
            run(
              optiscalerInstall,
              "Updating OptiScaler: progress shows under OptiScaler.",
              onOptiChange,
            )
          }
        >
          Update OptiScaler
        </ButtonItem>,
      );
    }
    const h = u.helixsr;
    if (h.error)
      rows.push(
        <Field
          key="he"
          label="HelixSR"
          description={`Couldn't check: ${h.error}`}
        />,
      );
    else if (h.update_available && h.available) {
      rows.push(
        <Field
          key="h"
          label={`HelixSR ${h.available} is available`}
          description={`You have ${h.installed}. Remove HelixSR from your games and add it again afterwards to use the new version.${pluginFirst ? FIRST : ""}`}
        />,
      );
      rows.push(
        <ButtonItem
          key="hb"
          layout="below"
          disabled={busy || pluginFirst}
          onClick={() =>
            run(
              () => helixsrInstall(h.available!),
              "Updating HelixSR: progress shows under HelixSR.",
              onHelixChange,
            )
          }
        >
          Update HelixSR
        </ButtonItem>,
      );
    }
    const m = u.mako;
    if (m.error)
      rows.push(
        <Field
          key="me"
          label="MAKO"
          description={`Couldn't check: ${m.error}`}
        />,
      );
    else if (m.update_available) {
      rows.push(
        <Field
          key="m"
          label={`MAKO ${m.available} is available`}
          description={`You have ${m.installed ?? "an older version"}.${pluginFirst ? FIRST : ""}`}
        />,
      );
      rows.push(
        <ButtonItem
          key="mb"
          layout="below"
          disabled={busy || pluginFirst}
          onClick={() => run(installMako, "MAKO updated.", onMakoChange)}
        >
          Update MAKO
        </ButtonItem>,
      );
    }
    // newer upstream releases than the ones this plugin carries: they come with a MultiFrameGen release
    const upstream = [
      o.newer_upstream && o.latest ? `Decky Framegen ${o.latest}` : null,
      m.newer_upstream && m.latest
        ? `MAKO ${m.latest.replace(/^plugin-/, "")}`
        : null,
    ].filter(Boolean);
    if (upstream.length) {
      rows.push(
        <Field
          key="up"
          label="Newer upstream releases"
          description={`${upstream.join(" and ")} ${upstream.length > 1 ? "are" : "is"} out. ${p.update_available ? "Update MultiFrameGen to check whether it brings them." : "They come with a future MultiFrameGen update."}`}
        />,
      );
    }
    if (!rows.length)
      rows.push(<Field key="ok" label="Everything is up to date" />);
  }

  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={checking || busy} onClick={check}>
          {checking ? "Checking for updates…" : "Check for updates"}
        </ButtonItem>
      </PanelSectionRow>
      {rows.map((r) => (
        <PanelSectionRow key={r.key}>{r}</PanelSectionRow>
      ))}
    </>
  );
}
