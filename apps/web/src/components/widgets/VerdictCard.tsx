import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

type Check = {
  name: string;
  status: string;
  score: number;
  detail?: string;
};

type Verdict = {
  decision: string;
  decision_reason: string;
  checks?: Check[];
  flags?: string[];
  recommendations?: string[];
};

const STYLE: Record<
  string,
  { cls: string; Icon: typeof CheckCircle2; label: string }
> = {
  approved: {
    cls: "border-emerald-600 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
    Icon: CheckCircle2,
    label: "Approved",
  },
  flagged: {
    cls: "border-amber-600 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
    Icon: AlertTriangle,
    label: "Flagged for review",
  },
  rejected: {
    cls: "border-rose-600 bg-rose-50 text-rose-900 dark:bg-rose-950 dark:text-rose-100",
    Icon: XCircle,
    label: "Rejected",
  },
};

export function VerdictCard({ verdict }: { verdict: Verdict }) {
  const [open, setOpen] = useState(false);
  const cfg = STYLE[verdict.decision] ?? STYLE.flagged;
  const { Icon } = cfg;

  return (
    <Card className={cn("border-2", cfg.cls)}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 font-semibold">
          <Icon className="h-5 w-5" aria-hidden /> {cfg.label}
        </div>
        <p className="text-sm">{verdict.decision_reason}</p>

        {verdict.recommendations && verdict.recommendations.length > 0 && (
          <>
            <Separator />
            <ul className="list-disc pl-5 text-sm space-y-1">
              {verdict.recommendations.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </>
        )}

        <button
          className="flex items-center gap-1 text-xs opacity-80 hover:opacity-100"
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronDown
            className={cn(
              "h-3 w-3 transition-transform",
              open && "rotate-180",
            )}
          />{" "}
          Why
        </button>
        {open && (
          <div className="text-xs space-y-1 font-mono">
            {verdict.checks?.map((c, i) => (
              <div key={i} className="flex justify-between gap-4">
                <span>{c.name}</span>
                <span>
                  {c.status} · {(c.score * 100).toFixed(0)}%
                </span>
              </div>
            ))}
            {verdict.flags && verdict.flags.length > 0 && (
              <div>
                <div className="pt-1 font-semibold">Flags</div>
                {verdict.flags.map((f, i) => (
                  <div key={i}>· {f}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
