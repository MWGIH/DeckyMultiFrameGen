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
- [ ] MAKO: install and per-game profiles.

## Install

On your Deck, in Decky's settings turn on **Developer mode**, then under **Developer** choose **Install Plugin from
URL** and enter:

```
https://github.com/MWGIH/DeckyMultiFrameGen/releases/latest/download/Decky-MultiFrameGen.zip
```

Or download `Decky-MultiFrameGen.zip` from the [latest release](https://github.com/MWGIH/DeckyMultiFrameGen/releases/latest)
and use **Install Plugin from ZIP**.

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
