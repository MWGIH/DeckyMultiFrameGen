import { callable } from "@decky/api";

export type BackendId = "optiscaler" | "helixsr" | "mako" | "fsr4injector" | "anrfg";
export type GameChoice =
  | "none"
  | "optiscaler"
  | "helixsr"
  | "mako"
  | "optiscaler+mako"
  | "helixsr+mako"
  | "optiscaler+helixsr"
  | "optiscaler+helixsr+mako"
  | "fsr4injector"
  | "fsr4injector+mako"
  | "anrfg";

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

export type GameSummary = { appid: string; name: string; non_steam?: boolean };

export type GameDetail = {
  ok: boolean;
  message?: string;
  appid?: string;
  name?: string | null;
  installed?: boolean;
  install_path?: string | null;
  backend?: GameChoice;
  choices?: GameChoice[];
  all_choices?: GameChoice[];
  upscalers?: string[] | null; // what the game ships (FSR 3.1+, DLSS, ...); null when its files couldn't be read
  files?: string[] | null; // the game's .exe and upscaler files, relative to its folder
  running_exes?: string[];
  notes_key?: string | null; // a non-Steam game known by its .exe: its key in GAME_NOTES // Windows programs running now (as Wine sees their paths)
  hidden?: { choice: GameChoice; needs: string[]; reason?: string | null }[];
  non_steam?: boolean; // a non-Steam game added to Steam
  folder_source?: "shortcut" | "heroic" | "lutris" | "picked" | null; // where its folder came from
  launcher?: string | null; // what starts it when it isn't the game's own .exe (Heroic, EA app, ...)
  browse_start?: string | null; // where the folder picker opens
};

export const getBackends = callable<[], Backend[]>("get_backends");
export const pluginVersion = callable<[], string>("plugin_version");
export const listInstalledGames = callable<
  [],
  { ok: boolean; message?: string; games: GameSummary[] }
>("list_installed_games");
export const getGame = callable<[appid: string], GameDetail>("get_game");
export const setGameFolder = callable<
  [appid: string, folder: string],
  { ok: boolean; error?: string; folder?: string | null; use_reset?: boolean }
>("set_game_folder");
export const setGameBackend = callable<
  [appid: string, backend: GameChoice, current_launch_options: string | null, dll_name: string],
  {
    ok: boolean;
    message?: string;
    backend?: GameChoice;
    removed?: string[];
    launch_options?: string | null;
    helix_in_opti?: HelixInOptiResult | null;
    fsr4?: Fsr4Result | null;
    // HelixSR put in on choosing HelixSR / HelixSR + MAKO (null when it was already in or needs a decision)
    helix?: { ok: boolean; error?: string; route?: string } | null;
    // OptiScaler patched in on choosing a choice with it (null when it already was or isn't installed)
    opti?: { ok: boolean; error?: string; dll_name?: string } | null;
    // ANR FG put in on choosing it (null when it already was or isn't installed)
    anr?: { ok: boolean; error?: string; proxy?: string } | null;
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
  // the optional extras this run builds, and how far each is
  extras?: HelixExtra[];
  extras_progress?: Partial<Record<HelixExtra, HelixExtraProgress>>;
};

export type HelixStatus = {
  job: HelixJob | null;
  log: string[];
  local: string[];
  active: string | null;
  active_ready: boolean;
  // false: the release has HLX FSR 4 (HelixSR 3.0 on) and its setup didn't build it
  active_hlx?: boolean | null;
  latest: HelixRelease | null;
  update_available: boolean;
  // pre-releases offered as updates (off by default), and a pre-release newer than the newest stable release
  prereleases?: boolean;
  newer_prerelease?: string | null;
  // optional extras of HelixSR's setup (HelixSR 3.3 on): switched on, offered by the release in use, built
  extras?: Record<HelixExtra, { on: boolean; available: boolean; built: boolean }>;
};

export type HelixExtra = "preset_k" | "vulkan";

export type HelixExtraProgress = {
  percent: number | null;
  step: string;
  state: "waiting" | "building" | "done" | "failed";
};

export type HelixRoute = "direct" | "scaler";

export type HelixGame = {
  ok: boolean;
  error?: string;
  found?: boolean;
  name?: string;
  route?: string | null;
  ways?: HelixRoute[];
  // ways testing found break this game (not offered), with why
  hidden_ways?: Partial<Record<HelixRoute, string>>;
  current?: string | null;
  installed?: boolean;
  label?: string;
  anticheat?: string[];
  scaler_name?: string | null;
  opti_logging?: boolean | null;
  launch_options_now?: string | null;
  graphics?: "vulkan" | null;
  // HelixSR's version in the game, and whether it's older than the release in use (installing again updates it)
  installed_version?: string | null;
  outdated?: boolean;
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
export const helixsrSetPrereleases = callable<
  [on: boolean],
  { ok: boolean; prereleases: boolean }
>("helixsr_set_prereleases");
export const helixsrSetExtra = callable<
  [name: HelixExtra, on: boolean],
  {
    ok: boolean;
    error?: string;
    started?: boolean;
  }
>("helixsr_set_extra");
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
export type OptiFsr4Files =
  | "deck"
  | "lite"
  | "exact"
  | "lossy"
  | "lite-exact"
  | "lite-lossy"
  | "decky"
  | "plain";
export type OptiFsr4State = {
  ok: boolean;
  error?: string;
  files: OptiFsr4Files;
  // what the game can be set to: Lite-like options only where they can work (or when already set)
  options: OptiFsr4Files[];
  // why Lite-like options can't work in the game, or null
  lite_unfit: string | null;
};
export const optiscalerFsr4Files = callable<[appid: string, files?: OptiFsr4Files], OptiFsr4State>(
  "optiscaler_fsr4_files",
);
export const optiscalerLogging = callable<
  [appid: string, on?: boolean],
  {
    ok: boolean;
    logging?: boolean | null;
    path?: string;
    log?: { lines: string[]; modified: number } | null;
    error?: string;
  }
>("optiscaler_logging");
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
  needs?: string | null;
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

// --- FSR4 Injector ---

export type Fsr4Gpu = {
  arch: string;
  model: string | null;
  model_name: string;
  verified: boolean;
};

export type Fsr4Job = {
  state: "running" | "done" | "failed";
  phase: "release" | "amd" | "done";
  done: number;
  total: number;
  version: string | null;
  error: string | null;
};

export type Fsr4Status = {
  version: string | null;
  unpacked: boolean;
  dll_ready: boolean;
  ready: boolean;
  gpu: Fsr4Gpu | null;
  recipe: { driver: string; fsr: string; dll_size: number } | null;
  eula_url: string;
  games: string[];
  job: Fsr4Job | null;
};

export type Fsr4Result = {
  ok: boolean;
  error?: string;
  launch_options?: string | null;
};

export type Fsr4Game = {
  ok: boolean;
  error?: string;
  unpacked?: boolean;
  ready?: boolean;
  found?: boolean;
  ffx_dll?: string | null;
  anticheat?: boolean;
  enabled?: boolean;
  verdict?: "ok" | "unused" | "failed" | "unknown" | null;
  reason?: string | null;
  watermark?: boolean;
  gpu_supported?: boolean;
};

export const fsr4Status = callable<[], Fsr4Status>("fsr4_status");
export const fsr4Install = callable<[], { ok: boolean; error?: string }>(
  "fsr4_install",
);
export const fsr4Remove = callable<[], { ok: boolean; error?: string }>(
  "fsr4_remove",
);
export const fsr4Games = callable<[], string[]>("fsr4_games");

export type Fsr4Details = {
  ok: boolean;
  error?: string;
  unpacked?: boolean;
  version?: string | null;
  folder?: string;
  gpu?:
    | (Fsr4Gpu & { pci?: string; family?: number; rev?: number })
    | null;
  amd?: {
    driver: string;
    fsr: string;
    file_version: string;
    size_mb: number;
    ready: boolean;
    path: string;
  };
  launch_options?: { plain: string; watermark: string };
  games?: {
    appid: string;
    name: string;
    target_dir: string;
    verdict: string;
    reason: string;
    watermark: boolean;
  }[];
};
export const fsr4Details = callable<[], Fsr4Details>("fsr4_details");
export const fsr4CompatibleGames = callable<
  [],
  {
    ok: boolean;
    error?: string;
    games: {
      appid: string;
      name: string;
      ffx_dll: string;
      anticheat: boolean;
      enabled: boolean;
    }[];
  }
>("fsr4_compatible_games");
export const fsr4GameStatus = callable<[appid: string], Fsr4Game>(
  "fsr4_game_status",
);
export const fsr4GameOn = callable<
  [appid: string, current_launch_options: string],
  Fsr4Result
>("fsr4_game_on");
export const fsr4GameOff = callable<
  [appid: string, current_launch_options: string],
  Fsr4Result
>("fsr4_game_off");
export const fsr4Watermark = callable<
  [appid: string, on: boolean, current_launch_options: string],
  Fsr4Result & { watermark?: boolean }
>("fsr4_watermark");

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
    test_builds?: boolean;
    url?: string | null;
    sha256?: string | null;
  };
  optiscaler: PartUpdate;
  helixsr: PartUpdate;
  mako: PartUpdate;
  fsr4injector?: PartUpdate;
  anrfg?: PartUpdate;
};
export const checkUpdates = callable<[], Updates>("check_updates");
export const getTestBuilds = callable<[], boolean>("get_test_builds");
export const setTestBuilds = callable<[on: boolean], boolean>("set_test_builds");

// --- ANR FG (Apex Neural Rendering) ---

export type AnrJob = {
  state: "running" | "done" | "failed";
  done: number;
  total: number;
  version: string | null;
  error: string | null;
  refreshed?: number;
};

export type AnrStatus = {
  version: string | null;
  ready: boolean;
  built_at: string | null;
  games: string[];
  job: AnrJob | null;
};

export type AnrGame = {
  ok: boolean;
  error?: string;
  ready?: boolean;
  enabled?: boolean;
  target_dir?: string | null;
  launch_option?: string | null;
  model_size?: string | null;
  log?: string | null;
};

export type AnrResult = {
  ok: boolean;
  error?: string;
  launch_options?: string | null;
};

export const anrStatus = callable<[], AnrStatus>("anr_status");
export const anrInstall = callable<[], { ok: boolean; error?: string }>("anr_install");
export const anrRemove = callable<[], { ok: boolean; error?: string }>("anr_remove");
export const anrGames = callable<[], string[]>("anr_games");
export const anrGameStatus = callable<[appid: string], AnrGame>("anr_game_status");
export const anrGameOn = callable<[appid: string, current_launch_options: string], AnrResult>("anr_game_on");
export const anrGameOff = callable<[appid: string, current_launch_options: string], AnrResult>("anr_game_off");
export const anrModelSize = callable<
  [appid: string, size: string],
  { ok: boolean; error?: string; model_size?: string | null }
>("anr_model_size");
