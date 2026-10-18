import { callable } from "@decky/api";

export type BackendId = "optiscaler" | "helixsr" | "mako";
export type GameChoice = "none" | "optiscaler" | "helixsr" | "optiscaler+helixsr" | "mako";

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
