# Credits

Decky MultiFrameGen brings three existing projects together in one Decky plugin. All the real work is theirs:
please star, support and report backend bugs to the original projects.

| Backend | Upstream plugin | Author | License | Used here |
| --- | --- | --- | --- | --- |
| [OptiScaler](https://github.com/optiscaler/OptiScaler) | [Decky Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen) | Kurt Himebauch (xXJSONDeruloXx) | BSD-3-Clause | Install and per-game patching logic, Steam library discovery |
| [HelixSR](https://github.com/lonewolf0622/HelixSR) | [HelixSR Manager](https://github.com/PeroTuncay/DeckyHelixSRManager) | PeroTuncay (plugin), lonewolf0622 (HelixSR) | Unlicense (plugin), HelixSR Freeware License | Release download, setup and per-game install logic, packaging script |
| [MAKO](https://github.com/eugeniosegala/MAKO) | MAKO Decky (same repo) | Eugenio Segala and contributors | GPL-3.0-or-later | Renderer install, per-game profiles and launch integration |

Because MAKO is GPL-3.0-or-later, this plugin as a whole is distributed under the
[GNU GPL version 3 or later](LICENSE). The upstream license texts are kept in [licenses/](licenses/).

## What this plugin does not contain

- **No OptiScaler, HelixSR or MAKO Renderer binaries.** Each backend is downloaded from its own official GitHub
  release on your device, so you always get the upstream build and updates follow the upstream projects.
- **No HelixSR files.** HelixSR's license allows redistributing only unmodified, complete official releases, so the
  plugin fetches them from [lonewolf0622/HelixSR](https://github.com/lonewolf0622/HelixSR/releases) and runs
  HelixSR's own setup.
- **No NVIDIA or Lossless Scaling files.** MAKO's frame generation reads resources from your own
  [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) install at runtime.

Decky MultiFrameGen is an independent integration and is not affiliated with or endorsed by the authors above,
NVIDIA, AMD, Lossless Scaling or Decky Loader.
