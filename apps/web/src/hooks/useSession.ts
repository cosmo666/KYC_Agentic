import { useCallback, useEffect, useState } from "react";

const KEY = "kyc.sessionId";
const EVENT = "kyc:session-changed";

/**
 * Multiple components (ChatShell, FaqDrawer, …) use this hook independently.
 * useState is per-instance, so a setter call in one component would NOT
 * propagate to another — leading to bugs like the FAQ drawer firing /chat
 * with sessionId=null because it never saw ChatShell's session-init.
 *
 * Fix: every update/reset dispatches a same-tab CustomEvent, and every hook
 * instance listens for it to keep its local state in sync. We also listen
 * for the native `storage` event to stay consistent across browser tabs.
 */
export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    sessionStorage.getItem(KEY),
  );

  useEffect(() => {
    const onCustom = (e: Event) => {
      setSessionId((e as CustomEvent<string | null>).detail ?? null);
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setSessionId(e.newValue);
    };
    window.addEventListener(EVENT, onCustom as EventListener);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT, onCustom as EventListener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const update = useCallback((id: string) => {
    sessionStorage.setItem(KEY, id);
    setSessionId(id);
    window.dispatchEvent(new CustomEvent(EVENT, { detail: id }));
  }, []);

  const reset = useCallback(() => {
    sessionStorage.removeItem(KEY);
    setSessionId(null);
    window.dispatchEvent(new CustomEvent(EVENT, { detail: null }));
  }, []);

  return { sessionId, update, reset };
}
