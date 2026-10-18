import { callable } from "@decky/api";

export type BackendId = "optiscaler" | "helixsr" | "mako";
export type GameChoice = "none" | "optiscaler" | "helixsr" | "mako";

export type Backend = {
  id: BackendId;
  name: string;
  plugin: string;
  repo: string;
  kind: string;
  installed: boolean;
  version: string | null;
  path?: string;
  releases?: string[];
  lossless_scaling?: boolean;
  notes?: string[];
  error?: string;
};

export type GameSummary = { appid: string; name: string };

export type GameDetail = {
  ok: boolean;
  message?: string;
  appid?: string;
  name?: string | null;
  installed?: boolean;
  install_path?: string | null;
  backend?: GameChoice;
  choices?: GameChoice[];
};

export const getBackends = callable<[], Backend[]>("get_backends");
export const listInstalledGames = callable<[], { ok: boolean; message?: string; games: GameSummary[] }>(
  "list_installed_games",
);
export const getGame = callable<[appid: string], GameDetail>("get_game");
export const setGameBackend = callable<
  [appid: string, backend: GameChoice],
  { ok: boolean; message?: string; backend?: GameChoice }
>("set_game_backend");
export const logError = callable<[message: string], void>("log_error");

// --- HelixSR ---

export type HelixRelease = { tag: string; name: string; url: string; size?: number; prerelease: boolean };

export type HelixJob = {
  state: "running" | "succeeded" | "failed";
  phase: "download" | "verify" | "extract" | "setup";
  tag: string;
  size?: number;
  downloaded?: number;
  error?: string | null;
};

export type HelixStatus = {
  job: HelixJob | null;
  log: string[];
  local: string[];
  active: string | null;
  active_ready: boolean;
  latest: HelixRelease | null;
  update_available: boolean;
};

export type HelixRoute = "direct" | "scaler";

export type HelixGame = {
  ok: boolean;
  error?: string;
  found?: boolean;
  name?: string;
  route?: string | null;
  ways?: HelixRoute[];
  current?: string | null;
  installed?: boolean;
  label?: string;
  anticheat?: string[];
  scaler_name?: string | null;
  in_game?: string;
  launch_options?: string | null;
  release?: string;
  log?: string[];
};

export const helixsrStatus = callable<[], HelixStatus>("helixsr_status");
export const helixsrInstall = callable<[tag?: string], { ok: boolean; error?: string; tag?: string }>(
  "helixsr_install",
);
export const helixsrGameStatus = callable<[appid: string], HelixGame>("helixsr_game_status");
export const helixsrInstallGame = callable<[appid: string, route?: string], HelixGame>("helixsr_install_game");
export const helixsrUninstallGame = callable<[appid: string], HelixGame>("helixsr_uninstall_game");
