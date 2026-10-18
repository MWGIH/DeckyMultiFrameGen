// Proxy DLL names and FSR4 runtime variants offered for OptiScaler, from Decky Framegen (BSD-3-Clause).

export const PROXY_DLL_OPTIONS = [
  { value: "dxgi.dll", label: "dxgi.dll (default)", hint: "Works for most DX12 games." },
  { value: "winmm.dll", label: "winmm.dll", hint: "Use when dxgi.dll conflicts with an existing game file." },
  { value: "version.dll", label: "version.dll", hint: "Common fallback; works well with many launchers." },
  { value: "dbghelp.dll", label: "dbghelp.dll", hint: "Use for debug helper hook paths." },
  { value: "winhttp.dll", label: "winhttp.dll", hint: "Use when other DLL names conflict." },
  { value: "wininet.dll", label: "wininet.dll", hint: "Use when other DLL names conflict." },
  { value: "OptiScaler.asi", label: "OptiScaler.asi", hint: "Needs an ASI loader already installed in the game." },
] as const;

export const FSR4_VARIANT_OPTIONS = [
  {
    value: "rdna23-int8",
    label: "4.0.2c | RDNA2/3 Compatibility",
    hint: "Older compatible runtime for RDNA2/3. In most cases, use the Valve 4.1.1 path for RDNA2 or the regular 4.1.1 driver override.",
  },
  {
    value: "rdna4-native",
    label: "4.1.1 | FFX 2.3 SDK",
    hint: "OptiScaler's bundled FSR 4.1.1 SDK upscaler. Official FSR4 support is RDNA4 (FP8) and RDNA3 desktop GPUs (INT8).",
  },
  {
    value: "rdna34-official-411",
    label: "4.1.1 | Driver Override",
    hint: "The FSR 4.1.1 SDK upscaler plus the 4.1.1 amdxcffx64.dll driver override.",
  },
  {
    value: "rdna2-valve-411-pre10",
    label: "4.1.1 | Valve RDNA2 Compatibility",
    hint: "FSR 4.1.1 with Valve's 4.1.1 amdxcffx64.dll and RDNA2-specific settings (the Steam Deck's GPU is RDNA2).",
  },
] as const;

export const DEFAULT_FSR4_VARIANT = "rdna23-int8";
