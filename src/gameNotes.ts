// What testing found for particular games (Steam app id): shown in the game's panel above its Use choice
export const GAME_NOTES: Record<string, string> = {
  "1091500":
    "Cyberpunk 2077 ships its own XeSS files. Plugin versions before 0.8.8 deleted them when OptiScaler was taken out, so the game then only started with OptiScaler. If it crashes at start, verify its files in Steam (Properties, Installed Files). FSR4 Injector doesn't work here: the game no longer offers FSR 3, so FSR 4 never becomes active; its options are hidden (Show all Use options still shows them).",
};
