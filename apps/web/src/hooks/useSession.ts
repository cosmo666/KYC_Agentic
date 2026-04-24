import { useCallback, useState } from "react";

const KEY = "kyc.sessionId";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    sessionStorage.getItem(KEY),
  );

  const update = useCallback((id: string) => {
    sessionStorage.setItem(KEY, id);
    setSessionId(id);
  }, []);

  const reset = useCallback(() => {
    sessionStorage.removeItem(KEY);
    setSessionId(null);
  }, []);

  return { sessionId, update, reset };
}
