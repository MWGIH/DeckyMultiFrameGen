import { ConfirmModal, showModal } from "@decky/ui";
import { toaster } from "@decky/api";

// MAKO's and HelixSR's installs only take effect after the Deck restarts
export function promptRestart(what: string, plural = false) {
  showModal(
    <ConfirmModal
      strTitle="Restart to finish"
      strDescription={plural
        ? `${what} are installed. Restart your Steam Deck before using them: they don't take effect until then.`
        : `${what} is installed. Restart your Steam Deck before using it: it doesn't take effect until then.`}
      strOKButtonText="Restart now"
      strCancelButtonText="Later"
      onOK={() => {
        const system = (
          window as unknown as {
            SteamClient?: { System?: { RestartPC?: () => void } };
          }
        ).SteamClient?.System;
        if (system?.RestartPC) system.RestartPC();
        else
          toaster.toast({
            title: "MultiFrameGen",
            body: "Couldn't restart from here: hold the power button and pick Restart.",
          });
      }}
    />,
  );
}
