# Credits

Decky MultiFrameGen brings four existing projects together in one Decky plugin. All the real work is theirs:
please star, support and report backend bugs to the original projects.

| Backend | Upstream plugin | Author | License | Used here |
| --- | --- | --- | --- | --- |
| [OptiScaler](https://github.com/optiscaler/OptiScaler) | [Decky Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen) | Kurt Himebauch (xXJSONDeruloXx) | BSD-3-Clause | Install and per-game patching logic, Steam library discovery |
| [HelixSR](https://github.com/lonewolf0622/HelixSR) | [HelixSR Manager](https://github.com/PeroTuncay/DeckyHelixSRManager) | PeroTuncay (plugin), lonewolf0622 (HelixSR) | Unlicense (plugin), HelixSR Freeware License | Release download, setup and per-game install logic, packaging script |
| [MAKO](https://github.com/eugeniosegala/MAKO) | MAKO Decky (same repo) | Eugenio Segala and contributors | GPL-3.0-or-later | MAKO Decky's backend (`py_modules/mako_plugin`) and frontend (`src/mako`) from tag `plugin-v4.6.0`, with small marked changes so its methods are prefixed `mako_` and the Renderer is downloaded at runtime |
| [FSR4 Injector](https://github.com/Rayekkk/FSR4Injector) | FSR4 Injector (same repo) | Rayekkk | BSD-3-Clause (plugin), LGPL-2.1-or-later (its `amdxc64.dll` shim) | Its release is downloaded at runtime and its own modules (`fsr4_dll`, `fsr4_install`, `fsr4_gpu`, `fsr4_games`) fetch AMD's library, read the GPU and install it per game |
| FSR 4.1.2 Lite for OptiScaler | — | Rayekkk (download method), optiscaler (OptiScaler nightly) | BSD-3-Clause (`py_modules/multifg/fsr4lite.py` reuses FSR4 Injector's `fsr4_dll` method and recipe), GPL-3.0 (OptiScaler) | The OptiScaler "FSR 4.1.2 Lite (AMD)" option: AMD's `amdxcffx64.dll` cut out of AMD's Adrenalin 26.10.1 installer on drivers.amd.com and checked by SHA-256, and `OptiScaler.dll` from [OptiScaler's nightly releases](https://github.com/optiscaler/OptiScaler-nightly/releases). Its Lite settings (`Fsr4GpuSupport=4`, `Fsr4Model=3`) follow OptiScaler's own `OptiScaler.ini` notes |
| FSR 4.1.2 Cyboman overrides | [fsr4-shader-performance-overrides](https://github.com/zgauthier2000/fsr4-shader-performance-overrides) | zgauthier2000 (Cyboman) | GPL-2.0-or-later (project scripts); modified AMD DLLs under AMD's notice in the release | OptiScaler options Exact / Lossy / Lite Exact / Lite Lossy: the Steam Deck / RDNA2 iGPU archive (`fsr4.1.2-igpu-cyboman-rdna2-*.7z`) is downloaded from that project's releases and checked by SHA-256. Single-player only |
| [Apex Neural Rendering](https://github.com/apex-compute/ANR) | ANR FG (same repo) | Apex Compute | Closed-source beta (no license stated); its OptiScaler build is GPL-3.0 with its source on each release | Its full package is downloaded at runtime and its own `install.sh` / `uninstall.sh` put ANR FG and Apex's OptiScaler into a game and take them out |

Because MAKO is GPL-3.0-or-later, this plugin as a whole is distributed under the
[GNU GPL version 3 or later](LICENSE). The upstream license texts are kept in [licenses/](licenses/).

## What this plugin does not contain

- **No OptiScaler, HelixSR or MAKO Renderer binaries.** Each backend is downloaded from its own official GitHub
  release on your device, so you always get the upstream build and updates follow the upstream projects.
- **No HelixSR files.** HelixSR's license allows redistributing only unmodified, complete official releases, so the
  plugin fetches them from [lonewolf0622/HelixSR](https://github.com/lonewolf0622/HelixSR/releases) and runs
  HelixSR's own setup.
- **No FSR4 Injector or AMD files.** FSR4 Injector's release (with its LGPL shim and that shim's source) is downloaded
  from [Rayekkk/FSR4Injector](https://github.com/Rayekkk/FSR4Injector/releases), and its code fetches AMD's FSR 4
  library (`amdxcffx64.dll`) from AMD's own driver package, under the
  [AMD Software EULA](https://www.amd.com/en/legal/eula/amd-software-eula.html) you accept when installing it.
  OptiScaler's "FSR 4.1.2 Lite (AMD)" option fetches the same AMD file the same way (or reuses FSR4 Injector's copy),
  under the same EULA, and never from a re-hosted copy.
- **No Cyboman binaries in the plugin zip.** The Cyboman `igpu-rdna2` archive is downloaded from
  [fsr4-shader-performance-overrides releases](https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases)
  on your device when you pick those FSR 4 options. They are modified / third-party FSR files: **single-player only**,
  never in online or anti-cheat games.
- **No ANR FG files.** ANR FG's full package (Apex's OptiScaler build with ANR FG as its frame generation provider) is
  downloaded from [apex-compute/ANR](https://github.com/apex-compute/ANR/releases) as released.
- **No NVIDIA or Lossless Scaling files.** MAKO's frame generation reads resources from your own
  [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) install at runtime.

Decky MultiFrameGen is an independent integration and is not affiliated with or endorsed by the authors above,
NVIDIA, AMD, Valve, Lossless Scaling or Decky Loader.
