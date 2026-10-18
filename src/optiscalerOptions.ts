// Proxy DLL names offered for OptiScaler, from Decky Framegen (BSD-3-Clause).

export const PROXY_DLL_OPTIONS = [
  { value: "dxgi.dll", label: "dxgi.dll (default)", hint: "Try this first. Works for most DirectX 11/12 games." },
  { value: "winmm.dll", label: "winmm.dll", hint: "First fallback: when the game won't start with dxgi.dll, ships its own, or is a Vulkan game." },
  { value: "version.dll", label: "version.dll", hint: "Second fallback; good for games that start through a launcher." },
  { value: "dbghelp.dll", label: "dbghelp.dll", hint: "For games with a crash reporter (many Unreal Engine games)." },
  { value: "winhttp.dll", label: "winhttp.dll", hint: "Last resort, for games that go online at start." },
  { value: "wininet.dll", label: "wininet.dll", hint: "Last resort, for games that go online at start." },
  { value: "OptiScaler.asi", label: "OptiScaler.asi", hint: "Needs an ASI loader already installed in the game." },
] as const;

// Games where the default dxgi.dll doesn't work, by Steam app id: the proxy DLL that does (see the README)
const PROXY_DLL_BY_GAME: Record<string, string> = {
  "1203620": "dbghelp.dll", // Enshrouded: won't start with dxgi.dll; winmm.dll and version.dll don't load OptiScaler
};

export const defaultProxyDll = (appid: string) => PROXY_DLL_BY_GAME[appid] ?? "dxgi.dll";

// The Steam Deck's GPU is RDNA2, so OptiScaler always uses Decky Framegen's "4.1.1 | Valve RDNA2 Compatibility" runtime.
export const FSR4_RUNTIME_LABEL = "FSR 4.1.1 (Valve RDNA2 compatibility)";
