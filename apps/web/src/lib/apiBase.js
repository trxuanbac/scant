export function resolveApiBase(configuredBase, isBrowser) {
  // Browser traffic stays on the current origin and is forwarded by the Next
  // rewrite. This also works when the UI is opened from another computer/LAN
  // address, where `localhost` would otherwise point to the viewer's device.
  return isBrowser ? "/api/v1" : String(configuredBase || "").replace(/\/$/, "");
}
