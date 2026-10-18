import { useState } from "react";
import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";

const KEY = "multifg:helixLogShown";

function saved(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

// HelixSR's log from the game: a one-line summary, the lines themselves only when shown (they take a lot of room).
export function HelixLog({
  log,
  missing,
}: {
  log?: { lines: string[]; modified: number } | null;
  missing: string;
}) {
  const [shown, setShown] = useState(saved);
  const toggle = () => {
    setShown(!shown);
    try {
      localStorage.setItem(KEY, shown ? "0" : "1");
    } catch {
      // the choice just isn't remembered
    }
  };
  if (!log) {
    return (
      <PanelSectionRow>
        <Field
          label="HelixSR hasn't run in this game yet"
          description={missing}
        />
      </PanelSectionRow>
    );
  }
  return (
    <>
      <PanelSectionRow>
        <Field
          label="HelixSR ran in this game"
          description={
            shown ? (
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {`${new Date(log.modified * 1000).toLocaleString()}\n${log.lines.join("\n")}`}
              </div>
            ) : (
              `Last log: ${new Date(log.modified * 1000).toLocaleString()}`
            )
          }
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={toggle}>
          {shown ? "Hide HelixSR log" : "Show HelixSR log"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
