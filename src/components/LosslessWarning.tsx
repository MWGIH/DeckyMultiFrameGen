import { ButtonItem, Field, Navigation, PanelSectionRow } from "@decky/ui";

const STORE_URL = "https://store.steampowered.com/app/993090/";

export const LOSSLESS_MISSING =
  "MAKO's frame generation runs on Lossless Scaling's DLL: without it, games get no generated frames (MAKO's scaling and shaders still work). Buy and install Lossless Scaling in Steam; it doesn't need to be run.";

// Shown wherever MAKO is in use while Lossless Scaling (Steam app 993090) isn't installed
export function LosslessWarning() {
  return (
    <>
      <PanelSectionRow>
        <Field label="⚠️ Lossless Scaling isn't installed" description={LOSSLESS_MISSING} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(STORE_URL)}>
          Open Lossless Scaling in the Steam Store
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
