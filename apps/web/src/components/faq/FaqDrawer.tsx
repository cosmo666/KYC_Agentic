import { useEffect, useState } from "react";
import { ArrowUp, HelpCircle, MessageSquareQuote, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sendChat } from "@/api/client";
import { useSession } from "@/hooks/useSession";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Why do you need my Aadhaar?",
  "Is my data safe?",
  "How long does this take?",
  "What happens after KYC?",
];

export function FaqDrawer() {
  const { sessionId } = useSession();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);

  // Esc to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const ask = async (text?: string) => {
    const value = (text ?? q).trim();
    if (!value) return;
    setBusy(true);
    try {
      // Trailing "?" nudges the intent classifier toward "faq".
      const res = await sendChat(
        value.endsWith("?") ? value : `${value}?`,
        sessionId,
      );
      const assistant = res.messages.find((m) => m.role === "assistant");
      setHistory((h) => [{ q: value, a: assistant?.content ?? "" }, ...h]);
      setQ("");
    } catch (err) {
      setHistory((h) => [
        { q: value, a: `Error: ${(err as Error).message}` },
        ...h,
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        aria-label="Open FAQ"
        onClick={() => setOpen(true)}
        className="fixed bottom-24 right-5 z-30 grid h-12 w-12 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-primary/20 transition-all hover:shadow-md hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <HelpCircle className="h-5 w-5" />
      </button>

      {/* Scrim */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-foreground/30 backdrop-blur-sm transition-opacity",
          open
            ? "opacity-100"
            : "pointer-events-none opacity-0",
        )}
        onClick={() => setOpen(false)}
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-label="Frequently asked questions"
        aria-modal="true"
        className={cn(
          "fixed inset-y-0 right-0 z-40 flex w-full max-w-[420px] flex-col bg-background shadow-lg transition-transform duration-200 ease-out border-l border-hairline",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between gap-2 border-b border-hairline px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-foreground">
              <MessageSquareQuote className="h-4 w-4" />
            </div>
            <div>
              <div className="text-[15px] font-semibold tracking-tight">
                Ask a question
              </div>
              <div className="text-[11px] text-muted-foreground">
                Compliance + KYC FAQ · grounded in RBI rules
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="grid h-9 w-9 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="border-b border-hairline p-4">
          <form
            className="flex items-center gap-2 rounded-xl border border-hairline bg-card px-2 py-1.5 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background"
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
          >
            <Input
              id="kyc-faq-input"
              name="faq-question"
              autoComplete="off"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask anything about KYC…"
              disabled={busy}
              aria-label="Ask a KYC question"
              className="border-0 bg-transparent shadow-none focus-visible:ring-0"
            />
            <Button
              type="submit"
              size="icon"
              disabled={busy || !q.trim()}
              className="h-8 w-8 rounded-lg active:scale-[0.96]"
              aria-label="Ask"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
          </form>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto px-4 py-4 text-sm">
          {history.length === 0 ? (
            <div className="space-y-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Suggested
              </div>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    disabled={busy}
                    className="rounded-full border border-hairline bg-card px-3 py-1.5 text-[12px] text-foreground/80 transition-colors hover:border-primary/40 hover:bg-accent hover:text-accent-foreground active:scale-[0.98] disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol className="space-y-5">
              {history.map((h, i) => (
                <li key={i} className="space-y-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    You asked
                  </div>
                  <div className="font-medium text-foreground">{h.q}</div>
                  <div className="rounded-lg border border-hairline bg-muted/40 px-3 py-2.5 text-foreground/90 whitespace-pre-wrap leading-relaxed">
                    {h.a}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </>
  );
}
