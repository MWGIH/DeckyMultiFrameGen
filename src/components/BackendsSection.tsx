import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import type { Backend, HelixStatus } from "../api";
import { HelixSRSetup } from "./HelixSRSetup";

function statusLine(b: Backend): string {
  if (b.error) return `Couldn't check: ${b.error}`;
  if (!b.installed) return "Not installed";
  return b.version ? `Installed (${b.version})` : "Installed";
}

type Props = { backends: Backend[] | null; helix: HelixStatus | null; onHelixChange: () => void };

export function BackendsSection({ backends, helix, onHelixChange }: Props) {
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
          </div>
        ))
      )}
    </PanelSection>
  );
}
