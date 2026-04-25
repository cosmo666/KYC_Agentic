import { useEffect, useState } from "react";

const KEY = "kyc.clientIp";

/**
 * Discover the user's *real* public IP and stash it in sessionStorage. We
 * send it on every backend call as X-Real-IP so the geolocation agent sees
 * the actual user IP instead of the docker bridge.
 *
 * Why not ipwho.is (the same service the backend uses)? Their free tier
 * blocks browser CORS — the request comes back 403 with
 * `{"message":"CORS is not supported on the Free plan"}`. So in the browser
 * we use api.ipify.org (free, no key, returns just the IP, CORS-enabled),
 * and the backend resolves country/city via ipwho.is from server-side
 * which has no CORS restriction.
 *
 * Returns the resolved IP (or null while loading / on failure) so the UI
 * can display it as a debug aid.
 */
export function useClientIP(): string | null {
  const [ip, setIp] = useState<string | null>(() => sessionStorage.getItem(KEY));

  useEffect(() => {
    if (ip) {
      console.info("[useClientIP] cached:", ip);
      return;
    }
    const ctrl = new AbortController();
    console.info("[useClientIP] resolving via api.ipify.org …");
    // Try ipify (CORS-friendly) first. If it ever changes, fall back to
    // icanhazip (text/plain, no JSON wrapper).
    const tryIpify = fetch("https://api.ipify.org?format=json", {
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: { ip?: string }) => d.ip || null);
    const tryIcanhazip = () =>
      fetch("https://icanhazip.com", { signal: ctrl.signal })
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((t) => t.trim() || null);

    tryIpify
      .catch((err) => {
        console.warn("[useClientIP] ipify failed, trying icanhazip:", err);
        return tryIcanhazip();
      })
      .then((resolved) => {
        if (resolved) {
          sessionStorage.setItem(KEY, resolved);
          setIp(resolved);
          console.info(`[useClientIP] resolved: ${resolved}`);
        } else {
          console.warn("[useClientIP] no IP returned from any provider");
        }
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        console.warn(
          "[useClientIP] all providers failed — backend will fall back to 8.8.8.8:",
          err,
        );
      });
    return () => ctrl.abort();
    // Run once on mount; ip changes via setIp inside.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return ip;
}

export function getClientIP(): string | null {
  return sessionStorage.getItem(KEY);
}
