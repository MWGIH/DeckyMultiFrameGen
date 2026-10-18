import { useState } from "react";
import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import type { Backend, HelixStatus, OptiStatus } from "../api";
import { HelixSRSetup } from "./HelixSRSetup";
import { OptiScalerSetup } from "./OptiScaler";

function statusLine(b: Backend): string {
  if (b.error) return `Couldn't check: ${b.error}`;
  if (!b.installed) return "Not installed";
  return b.version ? `Installed (${b.version})` : "Installed";
}

type Props = {
  backends: Backend[] | null;
  helix: HelixStatus | null;
  onHelixChange: () => void;
  opti: OptiStatus | null;
  onOptiChange: () => void;
  makoShown: boolean;
  onToggleMako: () => void;
};

const COLLAPSED_KEY = "multifg:backendsCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

// One line per backend while the section is hidden, e.g. "OptiScaler 0.9.4 · HelixSR v1.9.3 · MAKO not installed"
function summary(backends: Backend[]): string {
  return backends
    .map((b) => `${b.name} ${b.installed ? (b.version ?? "installed") : "not installed"}`)
    .join(" · ");
}

export function BackendsSection(props: Props) {
  const { backends, helix, onHelixChange, opti, onOptiChange, makoShown, onToggleMako } = props;
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // just not remembered
    }
  };
  return (
    <PanelSection title="Backends">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={toggle} description={collapsed && backends ? summary(backends) : undefined}>
          {collapsed ? "Show backends" : "Hide backends"}
        </ButtonItem>
      </PanelSectionRow>
      {collapsed ? null : backends === null ? (
        <PanelSectionRow>
          <Field label="Checking…" />
        </PanelSectionRow>
      ) : (
        backends.map((b) => (
          <div key={b.id}>
            <PanelSectionRow>
              <Field label={b.name} description={[b.kind, ...(b.notes ?? [])].join("\n")} bottomSeparator="standard">
                {statusLine(b)}
              </Field>
            </PanelSectionRow>
            {b.id === "helixsr" && <HelixSRSetup status={helix} onChange={onHelixChange} />}
            {b.id === "optiscaler" && <OptiScalerSetup status={opti} onChange={onOptiChange} />}
            {b.id === "mako" && (
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={onToggleMako}>
                  {makoShown ? "Hide MAKO's controls" : b.installed ? "Show MAKO's controls" : "Set up MAKO"}
                </ButtonItem>
              </PanelSectionRow>
            )}
          </div>
        ))
      )}
    </PanelSection>
  );
}
