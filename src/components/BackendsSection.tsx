import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import type { Backend } from "../api";

function statusLine(b: Backend): string {
  if (b.error) return `Couldn't check: ${b.error}`;
  if (!b.installed) return "Not installed";
  return b.version ? `Installed (${b.version})` : "Installed";
}

export function BackendsSection({ backends }: { backends: Backend[] | null }) {
  return (
    <PanelSection title="Backends">
      {backends === null ? (
        <PanelSectionRow>
          <Field label="Checking…" />
        </PanelSectionRow>
      ) : (
        backends.map((b) => (
          <PanelSectionRow key={b.id}>
            <Field label={b.name} description={[b.kind, ...(b.notes ?? [])].join("\n")} bottomSeparator="standard">
              {statusLine(b)}
            </Field>
          </PanelSectionRow>
        ))
      )}
    </PanelSection>
  );
}
