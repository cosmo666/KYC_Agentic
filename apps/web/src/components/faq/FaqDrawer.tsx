import { useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sendChat } from "@/api/client";
import { useSession } from "@/hooks/useSession";

export function FaqDrawer() {
  const { sessionId } = useSession();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    const text = q.trim();
    if (!text) return;
    setBusy(true);
    try {
      // Trailing "?" nudges the intent classifier toward "faq".
      const res = await sendChat(
        text.endsWith("?") ? text : `${text}?`,
        sessionId,
      );
      const assistant = res.messages.find((m) => m.role === "assistant");
      setHistory((h) => [{ q: text, a: assistant?.content ?? "" }, ...h]);
      setQ("");
    } catch (err) {
      setHistory((h) => [
        { q: text, a: `Error: ${(err as Error).message}` },
        ...h,
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        aria-label="Open FAQ"
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-6 h-12 w-12 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-lg hover:opacity-90"
      >
        <HelpCircle className="h-5 w-5" />
      </button>
      {open && (
        <div className="fixed inset-y-0 right-0 w-full sm:w-[400px] z-40 bg-background border-l flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div className="font-medium">Frequently asked</div>
            <button onClick={() => setOpen(false)} aria-label="Close FAQ">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="p-4 border-b flex gap-2">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask a KYC question…"
              onKeyDown={(e) => {
                if (e.key === "Enter") ask();
              }}
              disabled={busy}
            />
            <Button size="sm" onClick={ask} disabled={busy || !q.trim()}>
              Ask
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
            {history.length === 0 && (
              <div className="text-muted-foreground">
                Try: "Why do you need my Aadhaar?" · "Is my data safe?" · "How
                long does this take?"
              </div>
            )}
            {history.map((h, i) => (
              <div key={i}>
                <div className="font-medium">{h.q}</div>
                <div className="mt-1 whitespace-pre-wrap text-muted-foreground">
                  {h.a}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
