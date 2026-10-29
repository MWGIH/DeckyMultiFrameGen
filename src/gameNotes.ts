// What testing found for particular games (Steam app id): shown in the game's panel above its Use choice
export const GAME_NOTES: Record<string, string> = {
  "1091500":
    "HelixSR's FSR drop-in and FSR4 Injector both take away the game's own FSR 4 option, so neither is offered (Show all Use options still shows FSR4 Injector). Use HelixSR Scaler for HelixSR. Taking them out brings FSR 4 back.",
  "4115450":
    "OptiScaler only starts here with \"Without the FSR 4.1 Deck files\" on (it is by default): with them in, the game stops while starting. HelixSR doesn't work yet: HelixSR Scaler gets no depth image from the game (\"Upscaler failed to run!\") and the FSR drop-in isn't loaded.",
};
