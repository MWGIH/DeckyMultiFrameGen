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

Early development. Version 0.1 is the skeleton:

- [x] Detects the game you're on: the running game, else the game page open in your library, else one you pick.
- [x] Shows which backends are installed, including installs made by the original plugins.
- [x] Remembers which backend each game should use.
- [ ] Installs and updates each backend from its upstream releases, including HelixSR's setup (no Konsole needed).
- [ ] Applies the chosen backend to the game and writes its Steam launch options.

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
```

## License

[GPL-3.0-or-later](LICENSE). Upstream license texts are in [licenses/](licenses/).
