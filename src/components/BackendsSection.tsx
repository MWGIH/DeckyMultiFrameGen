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
  makoPinned: boolean;
  onToggleMako: () => void;
};

export function BackendsSection(props: Props) {
  const { backends, helix, onHelixChange, opti, onOptiChange, makoShown, makoPinned, onToggleMako } = props;
  return (
    <PanelSection title="Backends">
      {backends === null ? (
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
            {b.id === "mako" && !makoPinned && (
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
