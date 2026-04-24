import { useState } from "react";
import { SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function ChatInput({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  return (
    <form
      className="flex gap-2 border-t bg-background p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const t = text.trim();
        if (!t) return;
        onSend(t);
        setText("");
      }}
    >
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a message or ask a question…"
        disabled={disabled}
      />
      <Button type="submit" size="icon" disabled={disabled || !text.trim()}>
        <SendHorizontal className="h-4 w-4" />
      </Button>
    </form>
  );
}
