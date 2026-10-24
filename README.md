# Decky MultiFrameGen

Manage the best Decky frame gen add-ons all in one place: currently Decky Framegen (OptiScaler), MakoFG (MAKO) and HelixSR.

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for the Steam Deck and other SteamOS
devices that puts three frame generation and upscaling tools in one place, so you can pick which one each game uses
without juggling several plugins:

- **OptiScaler** (from [Decky Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen)): upscaling and frame
  generation for DirectX 12 games.
- **HelixSR** (from [HelixSR Manager](https://github.com/PeroTuncay/DeckyHelixSRManager)): DLSS-style upscaling on
  AMD GPUs, on its own or through OptiScaler.
- **MAKO** (from [MAKO](https://github.com/eugeniosegala/MAKO)): frame generation, scaling and shaders as a Vulkan
  layer. Frame generation needs [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/)
  installed in Steam; the scaler and shaders don't.

See [CREDITS.md](CREDITS.md) for who made what.

**See it in action:** the [Gaming On Steam](https://www.youtube.com/@gaming_onsteam) YouTube channel tests this plugin on
the Steam Deck, with game-by-game results and performance updates as it develops.

## Status

Early development.

- [x] Detects the game you're on: the running game, else the game page open in your library, else one you pick.
- [x] Shows which backends are installed, including installs made by the original plugins.
- [x] Remembers which backend each game should use.
- [x] HelixSR: downloads the official release, runs HelixSR's own setup from the plugin (no Konsole), and installs
      or removes it per game with HelixSR's own installer (FSR drop-in or HelixSR Scaler), setting launch options
      when needed.
- [x] OptiScaler: installs Decky Framegen's OptiScaler bundle (downloaded from the same upstream releases) and
      patches or unpatches games with Decky Framegen's own logic, setting launch options.
- [x] MAKO: MAKO Decky's full controls (install, profiles, frame generation, scaling, shaders, Flatpak and Remote
      Play setup) inside this plugin, with the MAKO Renderer downloaded from MAKO's releases; choosing MAKO for a game
      adds MAKO's launcher to its launch options.
- [x] Switching a game to another backend takes the previous one out of the game and restores its launch options.
- [x] OptiScaler + MAKO together: OptiScaler upscales in the game and MAKO's launcher goes into OptiScaler's launch
      options.
- [x] HelixSR + MAKO together: HelixSR upscales in the game (its own install) and MAKO's launcher stays in the game's
      launch options.
- [x] Backends checks that the MAKO Renderer is installed when MAKO is, and offers to install it if not.
- [x] MAKO updates: a daily GitHub Actions job (`.github/workflows/mako-update.yml`, `scripts/update_mako.py`) merges
      each new MAKO Decky release in and publishes a MultiFrameGen release, which Check for updates then offers.
- [x] Check for updates (Backends): updates this plugin through Decky's own installer, OptiScaler and MAKO to the
      versions this plugin brings, and HelixSR to its newest release. Newer Decky Framegen or MAKO releases are
      listed too; they arrive with the next MultiFrameGen release.
- [x] OptiScaler + HelixSR: HelixSR goes in as OptiScaler's FSR 3.X upscaler (OptiScaler.ini points FfxDx12Path at
      it), so the game's own files stay untouched. Use it in games whose anti-cheat blocks HelixSR's FSR drop-in
      (Easy Anti-Cheat in Gears of War: E-Day). Can be combined with MAKO.

If you also have MAKO Decky installed, keep only one of the two plugins enabled: both manage the same MAKO
Renderer install.

## OptiScaler: which proxy DLL to pick

A game never loads OptiScaler by itself. OptiScaler goes into the game's folder under the name of a Windows DLL the game
already loads (the "proxy DLL"), and Proton is told to load that copy instead of its own
(`WINEDLLOVERRIDES=<name>=n,b`, which the plugin puts in the launch options). Which name works depends on the game: it
has to be a DLL the game loads early, and one the game or its launcher doesn't mind being replaced.

| Proxy DLL | When to use it |
| --- | --- |
| `dxgi.dll` (default) | OptiScaler's recommended name and the one to try first. Every DirectX 11/12 game loads it. |
| `winmm.dll` | First fallback. Nearly every Windows game loads it (sound and timers), so it also works where `dxgi.dll` is the problem: the game ships its own `dxgi.dll`, another mod already uses that name, or the game crashes or won't start with it. |
| `version.dll` | Second fallback. Loaded by most games and launchers; a good choice when the game starts through a launcher. |
| `dbghelp.dll` | Loaded by games with crash reporters (many Unreal Engine games). Try it when the names above don't load OptiScaler. |
| `winhttp.dll`, `wininet.dll` | Loaded by games that go online at start (store, telemetry, news). Last resorts. |
| `OptiScaler.asi` | Only for games that already have an ASI loader (Ultimate ASI Loader); the loader loads OptiScaler. No launch option needed. |

If the game stops loading or crashes after patching, unpatch, pick the next name in this order and patch again:
`dxgi.dll`, `winmm.dll`, `version.dll`, `dbghelp.dll`, `winhttp.dll`, `wininet.dll`. If the game starts but OptiScaler's
menu never appears, the game doesn't load that name: try the next one too. If none works, OptiScaler can't hook the
game; MAKO still can, since it works outside the game.

OptiScaler mainly targets DirectX 11/12 games. A Vulkan game may not start with OptiScaler as `dxgi.dll`.
Enshrouded is one: only `dbghelp.dll` worked there (the plugin picks it for Enshrouded by default) (`winmm.dll` and `version.dll` started the game without loading
OptiScaler). Source: OptiScaler's
[Manual Installation](https://github.com/optiscaler/OptiScaler/wiki/Manual-Installation) guide (it lists the supported
names and prefers `dxgi.dll`); the fallback order is this plugin's advice.

## HelixSR game compatibility

HelixSR has no official compatibility list (its README says only that other GPUs, drivers and games are untested), so
this one collects what is known. The plugin checks each game itself and says in the game's panel when HelixSR can't
work there (Vulkan, no FSR / DLSS / XeSS files, anti-cheat).

What decides whether a game can use HelixSR:

| Game | HelixSR |
| --- | --- |
| DirectX 12 with FSR 3.1 | FSR drop-in (select AMD FSR in the game) |
| DirectX 12 with DLSS, XeSS or FSR 2 | HelixSR Scaler, or OptiScaler + HelixSR |
| DirectX 12 with anti-cheat that checks game files (Easy Anti-Cheat) | OptiScaler + HelixSR only; the drop-in stops the game |
| Vulkan, DirectX 11 or older, native Linux | Not supported |

OptiScaler + HelixSR uses HelixSR 1.9.3: HelixSR 2.0's DLL only runs inside its own OptiScaler build (HelixSR
Scaler 1.1.0), and the OptiScaler Decky Framegen installs (0.9.4) falls back to FSR 2.1.2 with it. The plugin sets
1.9.3 up next to 2.0 when needed.

Reports so far:

| Game | Way | Result | Source |
| --- | --- | --- | --- |
| Gears of War: E-Day | FSR drop-in | ❌ Easy Anti-Cheat splash, then a black screen | Steam Deck test for this plugin |
| Gears of War: E-Day | OptiScaler + HelixSR | ✅ Works, gets past Easy Anti-Cheat (select DLSS in the game, FSR 3.X in OptiScaler) | Steam Deck test for this plugin |
| Enshrouded | FSR drop-in, OptiScaler | ❌ HelixSR never loads (the game runs on Vulkan); OptiScaler works as `dbghelp.dll` (`dxgi.dll` stops the game loading; with `winmm.dll` or `version.dll` the game runs but OptiScaler doesn't load) | Steam Deck test for this plugin |
| Pragmata | not stated | ✅ 34 to 40 FPS, Steam Deck, performance mode | BlackHeart909, via [Wccftech](https://wccftech.com/helixsr-mod-dlss-3-7-steam-deck-amd-handhelds-faster-fsr-4/) |
| CONTROL Resonant | not stated | ✅ 35 to 40 FPS at 1080p, locked 60 at 720p, ROG Ally X | BlackHeart909, via [Wccftech](https://wccftech.com/helixsr-mod-dlss-3-7-steam-deck-amd-handhelds-faster-fsr-4/) |
| Hitman: World of Assassination | not stated | ✅ 35 FPS with DLSS Quality vs 17 with FSR 4, BC-250 at 4K | via [Wccftech](https://wccftech.com/helixsr-mod-dlss-3-7-steam-deck-amd-handhelds-faster-fsr-4/) |
| Diablo IV | FSR drop-in | ❌ Crashes on load | [HelixSR issue #1](https://github.com/lonewolf0622/HelixSR/issues/1) |
| Cyberpunk 2077 | HelixSR Scaler (HelixSR 2.0); MAKO alone | ✅ Runs after verifying the game's files. The crash at start came from versions before 0.8.8 deleting the game's own XeSS DLLs when OptiScaler was taken out | Steam Deck test for this plugin |
| Cyberpunk 2077 | OptiScaler, OptiScaler + HelixSR, OptiScaler + MAKO, OptiScaler + HelixSR + MAKO | ✅ Runs | Steam Deck test for this plugin |

Tried a game? Open an issue in this repository with the game, the way (FSR drop-in, HelixSR Scaler or OptiScaler +
HelixSR), the result, and the HelixSR log line from the game's panel.

## Install

On your Deck, in Decky's settings turn on **Developer mode**, then under **Developer** choose **Install Plugin from
URL** and enter:

```
https://github.com/MWGIH/DeckyMultiFrameGen/releases/latest/download/Decky-MultiFrameGen.zip
```

Or download a ZIP from the [latest release](https://github.com/MWGIH/DeckyMultiFrameGen/releases/latest) and use
**Install Plugin from ZIP**: `Decky-MultiFrameGen-SteamDeck.zip` for the Steam Deck, `Decky-MultiFrameGen-SteamFrame.zip`
for the Steam Frame. Both hold the same plugin (it has no native code); on the Steam Frame MAKO stays off because
its Renderer is x86_64 only. OptiScaler and HelixSR install Windows DLLs into games, which the Frame runs the same way.

## Releasing

Bump `version` in `package.json` and push to `main`: the build publishes release `v<version>` with the ZIP attached.

## Build

```sh
pnpm install
pnpm package        # builds out/Decky-MultiFrameGen.zip
pnpm typecheck
python3 -m unittest discover -s tests
# optional: HELIXSR_RELEASE_DIR=<extracted HelixSR release> runs HelixSR's real installer against test games,
# MULTIFG_NETWORK_TESTS=1 installs and patches OptiScaler end to end (downloads from upstream, needs 7z)
```

## License

[GPL-3.0-or-later](LICENSE). Upstream license texts are in [licenses/](licenses/).
