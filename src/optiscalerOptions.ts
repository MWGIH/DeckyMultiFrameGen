// Proxy DLL names offered for OptiScaler, from Decky Framegen (BSD-3-Clause).

export const PROXY_DLL_OPTIONS = [
  { value: "dxgi.dll", label: "dxgi.dll (default)", hint: "Works for most DX12 games." },
  { value: "winmm.dll", label: "winmm.dll", hint: "Use when dxgi.dll conflicts with an existing game file." },
  { value: "version.dll", label: "version.dll", hint: "Common fallback; works well with many launchers." },
  { value: "dbghelp.dll", label: "dbghelp.dll", hint: "Use for debug helper hook paths." },
  { value: "winhttp.dll", label: "winhttp.dll", hint: "Use when other DLL names conflict." },
  { value: "wininet.dll", label: "wininet.dll", hint: "Use when other DLL names conflict." },
  { value: "OptiScaler.asi", label: "OptiScaler.asi", hint: "Needs an ASI loader already installed in the game." },
] as const;

// The Steam Deck's GPU is RDNA2, so OptiScaler always uses Decky Framegen's "4.1.1 | Valve RDNA2 Compatibility" runtime.
export const FSR4_RUNTIME_LABEL = "FSR 4.1.1 (Valve RDNA2 compatibility)";
