import { useState } from "react";
import { Field, PanelSectionRow, ToggleField } from "@decky/ui";

function key(name: string): string {
  return name === "HelixSR"
    ? "multifg:helixLogShown"
    : `multifg:${name}LogShown`;
}

function saved(name: string): boolean {
  try {
    return localStorage.getItem(key(name)) === "1";
  } catch {
    return false;
  }
}

// HelixSR's (or OptiScaler's) log from the game: a one-line summary, the lines themselves only when shown (they take
// a lot of room).
export function HelixLog({
  log,
  missing,
  name = "HelixSR",
}: {
  log?: { lines: string[]; modified: number } | null;
  missing?: string;
  name?: string;
}) {
  const [shown, setShown] = useState(() => saved(name));
  const toggle = () => {
    setShown(!shown);
    try {
      localStorage.setItem(key(name), shown ? "0" : "1");
    } catch {
      // the choice just isn't remembered
    }
  };
  if (!log) {
    if (!missing) return null;
    return (
      <PanelSectionRow>
        <Field
          label={`${name} hasn't run in this game yet`}
          description={missing}
        />
      </PanelSectionRow>
    );
  }
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label={`Show ${name} log`}
          checked={shown}
          onChange={toggle}
          description={`${name} last ran in this game ${new Date(log.modified * 1000).toLocaleString()}`}
        />
      </PanelSectionRow>
      {shown && (
        <PanelSectionRow>
          <Field
            label={`${name} log`}
            description={
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {log.lines.join("\n")}
              </div>
            }
          />
        </PanelSectionRow>
      )}
    </>
  );
}
