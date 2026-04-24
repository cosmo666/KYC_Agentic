import { useState } from "react";
import { sendChat } from "@/api/client";
import type { ChatMessage } from "@/api/schemas";
import { useSession } from "@/hooks/useSession";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";

export function ChatShell() {
  const { sessionId, update } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const handle = async (text: string) => {
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const res = await sendChat(text, sessionId);
      if (!sessionId) update(res.session_id);
      setMessages((m) => [
        ...m,
        ...res.messages.filter((x) => x.role === "assistant"),
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `Error: ${(err as Error).message}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col max-w-2xl mx-auto">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="font-semibold">KYC Agent</div>
        {sessionId && (
          <div className="text-xs text-muted-foreground">
            #{sessionId.slice(0, 8)}
          </div>
        )}
      </header>
      <MessageList messages={messages} />
      <ChatInput onSend={handle} disabled={busy} />
    </div>
  );
}
