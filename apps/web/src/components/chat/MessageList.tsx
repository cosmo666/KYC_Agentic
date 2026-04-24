import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/api/schemas";
import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((m, i) => (
        <div key={i} className="space-y-2">
          <MessageBubble msg={m} />
          {/* widget slot — Phase 14 */}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
