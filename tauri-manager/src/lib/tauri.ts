/**
 * Safe wrapper around @tauri-apps/api/core's `invoke`.
 *
 * The real `invoke` only exists when the page is loaded inside a Tauri
 * webview window. During Vite-only previews (e.g. `preview_start` in
 * Claude's Preview plugin, or `npm run dev` alone), `window.__TAURI__`
 * is undefined and calling `invoke` throws a TypeError.
 *
 * In that non-Tauri preview mode we return a caller-supplied fallback
 * (usually an empty list or `null`), so the UI shell still renders
 * cleanly and we can iterate on polish without spinning up the full
 * native window.
 */

import { invoke as tauriInvoke } from "@tauri-apps/api/core";

/** True when the page is running inside a real Tauri window. */
export const isTauri = (): boolean =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function invoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
  fallback?: T,
): Promise<T> {
  if (!isTauri()) {
    if (fallback !== undefined) return fallback;
    throw new Error(
      `invoke("${cmd}") called outside Tauri and no fallback provided. ` +
        `In browser preview mode, pass a fallback value.`,
    );
  }
  return (await tauriInvoke(cmd, args)) as T;
}
