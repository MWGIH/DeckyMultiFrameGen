import { useState } from "react";
import { Field, PanelSectionRow, ToggleField } from "@decky/ui";

// The game's .exe and upscaler files with their folders: where a game keeps them decides where backends must go
export function GameFiles({ files, running }: { files?: string[] | null; running?: string[] }) {
  const [shown, setShown] = useState(false);
  if (!files?.length && !running?.length) return null;
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="Show the game's upscaler files"
          description="Its .exe and FSR, DLSS and XeSS files, with their folders."
          checked={shown}
          onChange={setShown}
        />
      </PanelSectionRow>
      {shown && (
        <PanelSectionRow>
          <Field
            label="Game files"
            description={
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {(files ?? []).join("\n")}
              </div>
            }
          />
        </PanelSectionRow>
      )}
      {shown && !!running?.length && (
        <PanelSectionRow>
          <Field
            label="Running now"
            description={
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {running.join("\n")}
              </div>
            }
          />
        </PanelSectionRow>
      )}
    </>
  );
}
