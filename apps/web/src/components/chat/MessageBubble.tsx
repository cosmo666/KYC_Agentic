import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/api/schemas";

const ERROR_PREFIX = "Error:";

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isError = !isUser && msg.content.startsWith(ERROR_PREFIX);

  if (isUser) {
    return (
      <div className="animate-msg-in flex w-full justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm whitespace-pre-wrap">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-msg-in flex w-full items-end gap-2.5">
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/15">
        <ShieldCheck className="h-4 w-4" aria-hidden />
      </div>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl rounded-bl-md border border-hairline px-4 py-2.5 text-sm leading-relaxed shadow-sm whitespace-pre-wrap",
          isError
            ? "border-destructive/30 bg-destructive/5 text-destructive"
            : "bg-card text-card-foreground",
        )}
      >
        {msg.content}
      </div>
    </div>
  );
}
