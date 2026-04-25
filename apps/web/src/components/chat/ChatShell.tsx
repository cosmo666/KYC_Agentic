import { useEffect, useState } from "react";
import { Moon, ShieldCheck, Sun, X } from "lucide-react";
import {
  captureImage,
  confirmDoc,
  getSession,
  initSession,
  sendChat,
  submitContact,
  uploadDoc,
} from "@/api/client";
import type { ChatMessage } from "@/api/schemas";
import { CameraCaptureModal } from "@/components/camera/CameraCaptureModal";
import { useClientIP } from "@/hooks/useClientIP";
import { useSession } from "@/hooks/useSession";
import { ChatInput } from "./ChatInput";
import { MessageList, type WidgetHandlers } from "./MessageList";

const THEME_KEY = "kyc.theme";

function useTheme(): ["light" | "dark", () => void] {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    localStorage.setItem(THEME_KEY, next);
    setTheme(next);
  };
  return [theme, toggle];
}

export function ChatShell() {
  const { sessionId, update, reset } = useSession();
  const [theme, toggleTheme] = useTheme();
  const clientIp = useClientIP();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [cameraTarget, setCameraTarget] = useState<"aadhaar" | "pan" | null>(
    null,
  );
  const [lastError, setLastError] = useState<{
    label: string;
    retry: () => void | Promise<void>;
  } | null>(null);

  useEffect(() => {
    const onOpen = (e: Event) => {
      const t = (e as CustomEvent).detail;
      if (t === "aadhaar" || t === "pan") setCameraTarget(t);
    };
    window.addEventListener("kyc:open-camera", onOpen);
    return () => window.removeEventListener("kyc:open-camera", onOpen);
  }, []);

  // Bootstrap the conversation:
  //  - With a sessionId in storage → rehydrate the prior thread from /session/{id}.
  //    On 4xx, fall through to a fresh init (the stored id is stale).
  //  - Without one → /session/init creates a session server-side and returns
  //    the agent's opening message + contact form widget.
  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      if (sessionId) {
        try {
          const res = await getSession(sessionId);
          if (!cancelled) setMessages(res.messages);
          return;
        } catch {
          // Stale id — clear it and fall through to init.
          reset();
        }
      }
      try {
        setBusy(true);
        const res = await initSession();
        if (cancelled) return;
        update(res.session_id);
        setMessages(res.messages);
      } catch (err) {
        if (cancelled) return;
        setMessages([
          {
            role: "assistant",
            content: `Error starting session: ${(err as Error).message}`,
          },
        ]);
      } finally {
        if (!cancelled) setBusy(false);
      }
    };
    void bootstrap();
    return () => {
      cancelled = true;
    };
    // Run on mount + whenever sessionId transitions (e.g. after Restart).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const appendAssistantFrom = (assistantMsgs: ChatMessage[]) => {
    setMessages((m) => [
      ...m,
      ...assistantMsgs.filter((x) => x.role === "assistant"),
    ]);
  };

  const sendText = async (text: string) => {
    setBusy(true);
    setLastError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const res = await sendChat(text, sessionId);
      if (!sessionId) update(res.session_id);
      appendAssistantFrom(res.messages);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `Error: ${(err as Error).message}` },
      ]);
      setLastError({ label: "Resend message", retry: () => sendText(text) });
    } finally {
      setBusy(false);
    }
  };

  const handlers: WidgetHandlers = {
    onContact: async (email, mobile) => {
      // The session was created by the prior /chat call (the greet turn).
      // Submitting the contact form advances the graph from wait_for_contact
      // to wait_for_name and emits the next assistant message.
      if (!sessionId) throw new Error("No active session.");
      setBusy(true);
      setLastError(null);
      setMessages((m) => [
        ...m,
        { role: "user", content: `Submitted contact details (${email}).` },
      ]);
      try {
        const res = await submitContact(sessionId, email, mobile);
        appendAssistantFrom(res.messages);
      } catch (err) {
        // Pop the optimistic "Submitted contact" line and re-throw so the
        // form can show its inline error; stash a banner-level retry too.
        setMessages((m) => m.slice(0, -1));
        setLastError({
          label: "Re-submit contact",
          retry: () => handlers.onContact(email, mobile),
        });
        throw err;
      } finally {
        setBusy(false);
      }
    },
    onUploadFile: async (docType, file) => {
      if (!sessionId) return;
      setBusy(true);
      setLastError(null);
      setMessages((m) => [
        ...m,
        { role: "user", content: `Uploaded ${docType} — ${file.name}` },
      ]);
      try {
        const res = await uploadDoc(sessionId, docType, file);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${(err as Error).message}` },
        ]);
        setLastError({
          label: `Re-upload ${docType}`,
          retry: () => handlers.onUploadFile(docType, file),
        });
      } finally {
        setBusy(false);
      }
    },
    onOpenCamera: (target) => {
      window.dispatchEvent(
        new CustomEvent("kyc:open-camera", { detail: target }),
      );
    },
    onConfirm: async (docType, fields) => {
      if (!sessionId) return;
      setBusy(true);
      setLastError(null);
      setMessages((m) => [
        ...m,
        { role: "user", content: `Confirmed ${docType} details.` },
      ]);
      try {
        const res = await confirmDoc(sessionId, docType, fields);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${(err as Error).message}` },
        ]);
        setLastError({
          label: `Re-confirm ${docType}`,
          retry: () => handlers.onConfirm(docType, fields),
        });
      } finally {
        setBusy(false);
      }
    },
    onSelfie: async (blob) => {
      if (!sessionId) return;
      setBusy(true);
      setLastError(null);
      setMessages((m) => [...m, { role: "user", content: "Captured selfie." }]);
      try {
        const res = await captureImage(sessionId, "selfie", blob);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${(err as Error).message}` },
        ]);
        setLastError({
          label: "Re-send selfie",
          retry: () => handlers.onSelfie(blob),
        });
      } finally {
        setBusy(false);
      }
    },
    onRestart: () => {
      reset();
      setMessages([]);
      setLastError(null);
    },
  };

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-hairline bg-background/80 px-4 py-3 backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <ShieldCheck className="h-[18px] w-[18px]" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-semibold leading-tight tracking-tight">
              KYC Agent
            </div>
            <div className="text-[11px] leading-tight text-muted-foreground">
              Indian identity verification
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {sessionId && (
            <span
              className="hidden items-center gap-1.5 rounded-full border border-hairline bg-muted/60 px-2.5 py-1 text-[11px] font-mono text-muted-foreground sm:inline-flex"
              title={sessionId}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              {sessionId.slice(0, 8)}
            </span>
          )}
          <span
            className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-mono sm:inline-flex ${
              clientIp
                ? "border-success/30 bg-success/10 text-success"
                : "border-warning/30 bg-warning/10 text-warning"
            }`}
            title={
              clientIp
                ? `Sending X-Real-IP: ${clientIp} on every API call`
                : "Could not detect public IP — backend will fall back to docker bridge"
            }
          >
            {clientIp ? `IP ${clientIp}` : "IP detecting…"}
          </span>
          <button
            type="button"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            onClick={toggleTheme}
            className="grid h-9 w-9 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            onClick={handlers.onRestart}
            className="rounded-md px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Restart
          </button>
        </div>
      </header>

      <MessageList messages={messages} handlers={handlers} busy={busy} />

      {lastError && (
        <div className="animate-slide-up flex items-center gap-2 border-t border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm">
          <span className="flex-1 truncate text-destructive">
            Last action failed — please try again.
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              const { retry } = lastError;
              setLastError(null);
              retry();
            }}
            className="rounded-md border border-destructive/40 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive hover:text-destructive-foreground active:scale-[0.98] disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-destructive focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {lastError.label}
          </button>
          <button
            type="button"
            onClick={() => setLastError(null)}
            aria-label="Dismiss error"
            className="grid h-7 w-7 place-items-center rounded-md text-destructive/70 transition-colors hover:bg-destructive/15 hover:text-destructive"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <ChatInput onSend={sendText} disabled={busy} />

      {cameraTarget && (
        <CameraCaptureModal
          open
          target={cameraTarget}
          onClose={() => setCameraTarget(null)}
          onCropped={async (blob) => {
            if (!sessionId) return;
            setBusy(true);
            setMessages((m) => [
              ...m,
              { role: "user", content: `Captured ${cameraTarget} image.` },
            ]);
            try {
              const res = await captureImage(sessionId, cameraTarget, blob);
              appendAssistantFrom(res.messages);
            } catch (err) {
              setMessages((m) => [
                ...m,
                {
                  role: "assistant",
                  content: `Error: ${(err as Error).message}`,
                },
              ]);
            } finally {
              setBusy(false);
            }
          }}
        />
      )}
    </div>
  );
}
