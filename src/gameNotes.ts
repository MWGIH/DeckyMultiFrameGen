// What testing found for particular games (Steam app id): shown in the game's panel above its Use choice
// Non-Steam games (whose app id differs per user) are keyed by their .exe, lower case (game_files.exe_key).
export const GAME_NOTES: Record<string, string> = {
  "soulframe.x64.exe":
    "MAKO works here. OptiScaler and HelixSR Scaler load, but Soulframe quits straight away (with every proxy DLL, and without the FSR 4.1 Deck files too), so they aren't offered. Soulframe's launcher also deletes DLLs it doesn't know from the game's folder; with Show all Use options, choosing OptiScaler or HelixSR starts Soulframe without its launcher. FSR 3 is built into the game (DX11 by default).",
  "1091500":
    "HelixSR's FSR drop-in and FSR4 Injector both take away the game's own FSR 4 option, so neither is offered (Show all Use options still shows FSR4 Injector). Use HelixSR Scaler for HelixSR. Taking them out brings FSR 4 back.",
  "4115450":
    "OptiScaler only starts here with \"Without the FSR 4.1 Deck files\" on (it is by default): with them in, the game stops while starting. HelixSR Scaler: the game first shows \"Upscaler failed to run!\"; change the upscaler in the game's graphics menu once and HelixSR then works. HelixSR's FSR drop-in isn't loaded here.",
};
