import { callable } from "@decky/api";

export type BackendId = "optiscaler" | "helixsr" | "mako";
export type GameChoice =
  | "none"
  | "optiscaler"
  | "helixsr"
  | "mako"
  | "optiscaler+mako"
  | "helixsr+mako"
  | "optiscaler+helixsr"
  | "optiscaler+helixsr+mako";

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
  renderer_installed?: boolean;
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
export const listInstalledGames = callable<
  [],
  { ok: boolean; message?: string; games: GameSummary[] }
>("list_installed_games");
export const getGame = callable<[appid: string], GameDetail>("get_game");
export const setGameBackend = callable<
  [appid: string, backend: GameChoice, current_launch_options: string | null],
  {
    ok: boolean;
    message?: string;
    backend?: GameChoice;
    removed?: string[];
    launch_options?: string | null;
    helix_in_opti?: HelixInOptiResult | null;
  }
>("set_game_backend");
export const logError = callable<[message: string], void>("log_error");

// --- MAKO (its own panel calls mako_* through src/mako/api/makoApi.ts) ---

export const makoGames = callable<[], string[]>("mako_games");
export const makoGameLaunchOptions = callable<
  [current_launch_options: string, enable: boolean],
  {
    ok: boolean;
    error?: string;
    installed: boolean;
    launch_options?: string;
    enabled?: boolean;
    runner?: string;
  }
>("mako_game_launch_options");

// --- HelixSR ---

export type HelixRelease = {
  tag: string;
  name: string;
  url: string;
  size?: number;
  prerelease: boolean;
};

export type HelixJob = {
  state: "running" | "succeeded" | "failed";
  phase: "download" | "verify" | "extract" | "setup";
  tag: string;
  size?: number;
  downloaded?: number;
  error?: string | null;
  setup_percent?: number | null; // HelixSR's setup: its network build bar, null before the build starts
  setup_step?: string | null;
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
  opti_logging?: boolean | null;
  graphics?: "vulkan" | null;
  runtime_log?: { path: string; modified: number; lines: string[] } | null;
  in_game?: string;
  launch_options?: string | null;
  release?: string;
  log?: string[];
};

export const helixsrStatus = callable<[], HelixStatus>("helixsr_status");
export const helixsrLog = callable<
  [lines?: number],
  { path: string; lines: string[] }
>("helixsr_log");
export const helixsrInstall = callable<
  [tag?: string],
  { ok: boolean; error?: string; tag?: string }
>("helixsr_install");
export const helixsrRemove = callable<
  [],
  { ok: boolean; error?: string; removed?: string[] }
>("helixsr_remove");
export const helixsrGameStatus = callable<[appid: string], HelixGame>(
  "helixsr_game_status",
);
export const helixsrInstallGame = callable<
  [appid: string, route: string, current_launch_options: string],
  HelixGame & { removed?: string[]; base_launch_options?: string | null }
>("helixsr_install_game");
export const helixsrScalerLogging = callable<
  [appid: string, on: boolean],
  { ok: boolean; logging?: boolean | null; error?: string }
>("helixsr_scaler_logging");
export const helixsrUninstallGame = callable<[appid: string], HelixGame>(
  "helixsr_uninstall_game",
);

// HelixSR as a mod inside OptiScaler (OptiScaler's FSR 3.1 upscaler is HelixSR)
export type HelixInOptiResult = {
  ok: boolean;
  error?: string;
  installed?: boolean;
  removed?: boolean;
};
export type HelixInOpti = {
  ok: boolean;
  error?: string;
  patched?: boolean;
  installed?: boolean;
  ini_ok?: boolean;
  helixsr?: string | null;
  active?: string | null;
  runtime_log?: { lines: string[]; modified: number } | null;
};
export const helixsrOptiStatus = callable<[appid: string], HelixInOpti>(
  "helixsr_opti_status",
);
export const helixsrOptiAdd = callable<[appid: string], HelixInOptiResult>(
  "helixsr_opti_add",
);
export const helixsrOptiRemove = callable<[appid: string], HelixInOptiResult>(
  "helixsr_opti_remove",
);

// --- OptiScaler (Decky Framegen) ---

export type OptiStatus = {
  exists: boolean;
  version?: string | null;
  selected_fsr4_variant?: string | null;
  selected_fsr4_variant_label?: string | null;
  install_manifest_present?: boolean;
  legacy?: boolean;
  job?: OptiJob | null;
};

export type OptiJob = {
  state: "running" | "done" | "failed";
  phase: "download" | "install";
  asset: string | null;
  downloaded: number;
  size: number;
  message: string | null;
};

export type OptiResult = {
  status: string;
  message?: string;
  output?: string;
  version?: string;
};

export type OptiGame = {
  status: string;
  message?: string;
  name?: string;
  install_found?: boolean;
  patched?: boolean;
  dll_name?: string | null;
  fsr4_variant?: string | null;
  fsr4_variant_label?: string | null;
  optiscaler_version?: string | null;
};

export type OptiPatch = OptiResult & {
  launch_options?: string;
  original_launch_options?: string;
  removed?: string[];
  helix_in_opti?: HelixInOptiResult;
};

export const optiscalerStatus = callable<[], OptiStatus>("optiscaler_status");
export const optiscalerInstall = callable<[], OptiResult>("optiscaler_install");
export const optiscalerUninstall = callable<[], OptiResult>(
  "optiscaler_uninstall",
);
export const optiscalerGameStatus = callable<[appid: string], OptiGame>(
  "optiscaler_game_status",
);
export const optiscalerPatchGame = callable<
  [appid: string, dll_name: string, current_launch_options: string],
  OptiPatch
>("optiscaler_patch_game");
export const optiscalerUnpatchGame = callable<[appid: string], OptiPatch>(
  "optiscaler_unpatch_game",
);

// --- updates ---

export type PartUpdate = {
  error?: string;
  installed?: string | null;
  available?: string | null;
  update_available?: boolean;
  latest?: string | null; // newest upstream release (Decky Framegen, MAKO)
  newer_upstream?: boolean;
};
export type Updates = {
  plugin: {
    error?: string;
    current?: string;
    latest?: string | null;
    update_available?: boolean;
    url?: string | null;
    sha256?: string | null;
  };
  optiscaler: PartUpdate;
  helixsr: PartUpdate;
  mako: PartUpdate;
};
export const checkUpdates = callable<[], Updates>("check_updates");
