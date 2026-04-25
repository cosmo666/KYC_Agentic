import { useState } from "react";
import {
  captureImage,
  confirmDoc,
  sendChat,
  uploadDoc,
} from "@/api/client";
import type { ChatMessage } from "@/api/schemas";
import { useSession } from "@/hooks/useSession";
import { ChatInput } from "./ChatInput";
import { MessageList, type WidgetHandlers } from "./MessageList";

export function ChatShell() {
  const { sessionId, update, reset } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const appendAssistantFrom = (assistantMsgs: ChatMessage[]) => {
    setMessages((m) => [
      ...m,
      ...assistantMsgs.filter((x) => x.role === "assistant"),
    ]);
  };

  const sendText = async (text: string) => {
    setBusy(true);
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
    } finally {
      setBusy(false);
    }
  };

  const handlers: WidgetHandlers = {
    onUploadFile: async (docType, file) => {
      if (!sessionId) return;
      setBusy(true);
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
      } finally {
        setBusy(false);
      }
    },
    onOpenCamera: (target) => {
      // Wired up to the camera modal in Phase 15.
      window.dispatchEvent(new CustomEvent("kyc:open-camera", { detail: target }));
    },
    onConfirm: async (docType, fields) => {
      if (!sessionId) return;
      setBusy(true);
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
      } finally {
        setBusy(false);
      }
    },
    onSelfie: async (blob) => {
      if (!sessionId) return;
      setBusy(true);
      setMessages((m) => [...m, { role: "user", content: "Captured selfie." }]);
      try {
        const res = await captureImage(sessionId, "selfie", blob);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${(err as Error).message}` },
        ]);
      } finally {
        setBusy(false);
      }
    },
    onRestart: () => {
      reset();
      setMessages([]);
    },
  };

  return (
    <div className="flex h-full flex-col max-w-2xl mx-auto">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="font-semibold">KYC Agent</div>
        <div className="flex items-center gap-3">
          {sessionId && (
            <div className="text-xs text-muted-foreground">
              #{sessionId.slice(0, 8)}
            </div>
          )}
          <button
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={handlers.onRestart}
          >
            Restart
          </button>
        </div>
      </header>
      <MessageList messages={messages} handlers={handlers} />
      <ChatInput onSend={sendText} disabled={busy} />
    </div>
  );
}
