import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Globe,
  ListChecks,
  MapPin,
  ScanFace,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Users,
  XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { MapPreview } from "@/components/widgets/MapPreview";
import type { FaceCheck, IpCheck } from "@/api/schemas";

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
  ip_check?: IpCheck | null;
  face_check?: FaceCheck | null;
  selfie_url?: string | null;
  aadhaar_face_url?: string | null;
};

const API_BASE =
  (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ??
  "http://localhost:8000";

function absUrl(rel: string | null | undefined): string | null {
  if (!rel) return null;
  if (/^https?:/i.test(rel)) return rel;
  return `${API_BASE}${rel.startsWith("/") ? "" : "/"}${rel}`;
}

type DecisionStyle = {
  bar: string;
  badge: string;
  badgeText: string;
  Icon: typeof CheckCircle2;
  label: string;
  tone: "approved" | "flagged" | "rejected";
};

const DECISION: Record<string, DecisionStyle> = {
  approved: {
    bar: "bg-success",
    badge: "bg-success/10 text-success ring-success/20",
    badgeText: "Approved",
    Icon: ShieldCheck,
    label: "Approved",
    tone: "approved",
  },
  flagged: {
    bar: "bg-warning",
    badge: "bg-warning/10 text-warning ring-warning/20",
    badgeText: "Flagged for review",
    Icon: ShieldAlert,
    label: "Flagged for review",
    tone: "flagged",
  },
  rejected: {
    bar: "bg-destructive",
    badge: "bg-destructive/10 text-destructive ring-destructive/20",
    badgeText: "Rejected",
    Icon: ShieldX,
    label: "Rejected",
    tone: "rejected",
  },
};

const CHECK_LABEL: Record<string, string> = {
  name_match: "Name match",
  dob_match: "Date of birth",
  doc_type_sanity: "Document types",
  ocr_confidence: "OCR confidence",
};

export function VerdictCard({ verdict }: { verdict: Verdict }) {
  const cfg = DECISION[verdict.decision] ?? DECISION.flagged;
  const { Icon } = cfg;

  return (
    <Card className="overflow-hidden border-hairline shadow-lg">
      {/* Status hero — colored top bar + icon + badge */}
      <div className={cn("h-1 w-full", cfg.bar)} />
      <CardContent className="space-y-5 p-5">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "grid h-12 w-12 shrink-0 place-items-center rounded-xl ring-1",
              cfg.badge,
            )}
          >
            <Icon className="h-6 w-6" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <div
              className={cn(
                "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ring-1",
                cfg.badge,
              )}
            >
              {cfg.badgeText}
            </div>
            <h3 className="mt-1.5 text-lg font-semibold tracking-tight">
              {verdict.decision_reason || "Verification complete."}
            </h3>
          </div>
        </div>

        {/* Per-stage cards in the order the agents ran:
              1) face match  →  2) gender match  →  3) location.
            Each stage shows independently so the user can SEE which check
            tripped the verdict (especially when the country gate fires
            early and rejects regardless of face quality). */}
        {verdict.face_check && verdict.face_check.faces_detected != null && (
          <FaceMatchRow
            face={verdict.face_check}
            aadhaarFaceUrl={absUrl(verdict.aadhaar_face_url)}
            selfieUrl={absUrl(verdict.selfie_url)}
          />
        )}
        {verdict.face_check && verdict.face_check.aadhaar_gender && (
          <GenderMatchRow face={verdict.face_check} />
        )}
        {verdict.ip_check && verdict.ip_check.ip && (
          <LocationCard ipCheck={verdict.ip_check} />
        )}

        {/* Recommendations / next steps */}
        {verdict.recommendations && verdict.recommendations.length > 0 && (
          <Section title="Next steps">
            <ul className="space-y-1.5 text-sm leading-relaxed text-foreground/90">
              {verdict.recommendations.map((r, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Validation checks — collapsible */}
        {verdict.checks && verdict.checks.length > 0 && (
          <ChecksSection checks={verdict.checks} flags={verdict.flags ?? []} />
        )}
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <Separator className="mb-4" />
      <div className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}

function StageRow({
  Icon,
  label,
  detail,
  status,
  badge,
}: {
  Icon: typeof ScanFace;
  label: string;
  detail: string;
  status: "pass" | "warn" | "fail" | "unknown";
  badge: string;
}) {
  const tone = {
    pass: {
      cls: "bg-success/10 text-success ring-success/20",
      pillCls: "bg-success/10 text-success ring-success/20",
    },
    warn: {
      cls: "bg-warning/10 text-warning ring-warning/20",
      pillCls: "bg-warning/10 text-warning ring-warning/20",
    },
    fail: {
      cls: "bg-destructive/10 text-destructive ring-destructive/20",
      pillCls: "bg-destructive/10 text-destructive ring-destructive/20",
    },
    unknown: {
      cls: "bg-muted text-muted-foreground ring-border",
      pillCls: "bg-muted text-muted-foreground ring-border",
    },
  }[status];
  return (
    <div className="flex items-center gap-3 rounded-xl border border-hairline bg-muted/40 px-4 py-3">
      <div
        className={cn(
          "grid h-10 w-10 shrink-0 place-items-center rounded-lg ring-1",
          tone.cls,
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="mt-0.5 text-[12px] text-muted-foreground">{detail}</div>
      </div>
      <div
        className={cn(
          "shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1",
          tone.pillCls,
        )}
      >
        {badge}
      </div>
    </div>
  );
}

function FaceMatchRow({
  face,
  aadhaarFaceUrl,
  selfieUrl,
}: {
  face: FaceCheck;
  aadhaarFaceUrl: string | null;
  selfieUrl: string | null;
}) {
  const facesDetected = face.faces_detected ?? false;
  const verified = face.verified ?? false;
  const confidence = face.confidence ?? 0;
  // VGG-Face returns its own threshold (~0.68 for cosine); we treat verified
  // OR confidence >= 60 as "passing" downstream — mirror that here.
  const status: "pass" | "warn" | "fail" = !facesDetected
    ? "fail"
    : verified || confidence >= 60
      ? "pass"
      : "warn";
  const badge =
    status === "fail" ? "FAIL" : status === "pass" ? "MATCH" : "LOW";
  const tone = {
    pass: {
      ring: "ring-success/30",
      bar: "bg-success",
      pill: "bg-success/10 text-success ring-success/20",
      glow: "from-success/20 via-success/40 to-success/20",
    },
    warn: {
      ring: "ring-warning/30",
      bar: "bg-warning",
      pill: "bg-warning/10 text-warning ring-warning/20",
      glow: "from-warning/20 via-warning/40 to-warning/20",
    },
    fail: {
      ring: "ring-destructive/30",
      bar: "bg-destructive",
      pill: "bg-destructive/10 text-destructive ring-destructive/20",
      glow: "from-destructive/20 via-destructive/40 to-destructive/20",
    },
  }[status];

  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-muted/40">
      <div className="flex items-center gap-2 border-b border-hairline px-4 py-2.5">
        <ScanFace className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Face match</span>
        <span
          className={cn(
            "ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1",
            tone.pill,
          )}
        >
          {badge}
        </span>
      </div>

      <div className="flex items-center justify-center gap-3 px-4 py-4">
        <FaceThumb
          src={aadhaarFaceUrl}
          label="Aadhaar"
          ringClass={tone.ring}
        />
        <ScanLink toneGlow={tone.glow} confidence={confidence} />
        <FaceThumb src={selfieUrl} label="Selfie" ringClass={tone.ring} />
      </div>

      <div className="space-y-1.5 px-4 pb-4">
        <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn("h-full transition-all duration-700 ease-out", tone.bar)}
            style={{ width: `${Math.min(100, Math.max(2, confidence))}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>
            {facesDetected
              ? "Selfie compared with the cropped Aadhaar photo"
              : "No face detected in the selfie"}
          </span>
          <span className="font-mono font-medium text-foreground">
            {confidence.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

function FaceThumb({
  src,
  label,
  ringClass,
}: {
  src: string | null;
  label: string;
  ringClass: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={cn(
          "relative h-16 w-16 overflow-hidden rounded-full bg-muted ring-2 ring-offset-2 ring-offset-background shadow-sm",
          ringClass,
        )}
      >
        {src ? (
          <img
            src={src}
            alt={`${label} face`}
            className="h-full w-full object-cover"
            crossOrigin="anonymous"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="grid h-full w-full place-items-center text-muted-foreground">
            <ScanFace className="h-5 w-5" />
          </div>
        )}
      </div>
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

function ScanLink({
  toneGlow,
  confidence,
}: {
  toneGlow: string;
  confidence: number;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-16 w-20">
        {/* Two horizontal channels with a moving "scanner" pulse — visualises
            the comparison without claiming live analysis. */}
        <div className="absolute left-0 right-0 top-1/2 -translate-y-3 h-px bg-border" />
        <div className="absolute left-0 right-0 top-1/2 translate-y-3 h-px bg-border" />
        <div
          className={cn(
            "absolute left-0 right-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full bg-gradient-to-r opacity-80",
            toneGlow,
          )}
        >
          <div className="absolute inset-y-0 left-0 w-6 bg-white/30 [animation:scan-flow_1.8s_linear_infinite] dark:bg-white/15" />
        </div>
        <div className="absolute inset-0 grid place-items-center">
          <span className="rounded-md bg-background px-1.5 py-0.5 font-mono text-[10px] font-semibold ring-1 ring-border">
            {confidence.toFixed(0)}%
          </span>
        </div>
      </div>
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Compared
      </span>
    </div>
  );
}

function GenderMatchRow({ face }: { face: FaceCheck }) {
  const aadhaar = (face.aadhaar_gender ?? "").toLowerCase();
  const predicted = (face.predicted_gender ?? "").toLowerCase();
  const match = face.gender_match;
  const status: "pass" | "warn" | "fail" | "unknown" =
    match === true ? "pass" : match === false ? "fail" : "unknown";
  const detail =
    aadhaar && predicted
      ? `Aadhaar: ${aadhaar} · Selfie: ${predicted}`
      : "Could not compare gender";
  const badge =
    status === "pass" ? "MATCH" : status === "fail" ? "MISMATCH" : "—";
  return (
    <StageRow
      Icon={Users}
      label="Gender match"
      detail={detail}
      status={status}
      badge={badge}
    />
  );
}

function LocationCard({ ipCheck }: { ipCheck: IpCheck }) {
  const ok = ipCheck.country_ok ?? false;
  const cc = (ipCheck.country_code ?? "??").toUpperCase();
  const place = [ipCheck.city, ipCheck.region].filter(Boolean).join(", ") || "Unknown";
  const lat = ipCheck.latitude;
  const lng = ipCheck.longitude;
  const hasCoords = typeof lat === "number" && typeof lng === "number";

  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-muted/40">
      <div className="relative flex items-center justify-between gap-4 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={cn(
              "grid h-10 w-10 shrink-0 place-items-center rounded-lg ring-1",
              ok
                ? "bg-success/10 text-success ring-success/20"
                : "bg-destructive/10 text-destructive ring-destructive/20",
            )}
          >
            <Globe className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{place}</span>
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[12px] text-muted-foreground">
              <span className="font-mono">{ipCheck.ip}</span>
              <span className="rounded-md bg-background px-1.5 py-px font-mono text-[10px] font-semibold tracking-wider ring-1 ring-border">
                {cc}
              </span>
              {hasCoords && (
                <span className="hidden font-mono text-[10px] sm:inline">
                  {lat!.toFixed(3)}, {lng!.toFixed(3)}
                </span>
              )}
            </div>
          </div>
        </div>
        <div
          className={cn(
            "shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1",
            ok
              ? "bg-success/10 text-success ring-success/20"
              : "bg-destructive/10 text-destructive ring-destructive/20",
          )}
        >
          {ok ? "India" : "Outside India"}
        </div>
      </div>
      {/* Real OSM map when ipwho.is gave us coords; fall back to the dot
          strip otherwise so the card doesn't show an empty rectangle. */}
      {hasCoords ? (
        <div className="border-t border-hairline">
          <MapPreview
            lat={lat!}
            lng={lng!}
            label={place}
            className="h-44 w-full overflow-hidden"
          />
        </div>
      ) : (
        <div className="relative h-8 overflow-hidden border-t border-hairline">
          <WorldStrip highlight={ok} />
        </div>
      )}
    </div>
  );
}

function WorldStrip({ highlight }: { highlight: boolean }) {
  // Hand-tuned dot grid that vaguely reads as continents — a refined,
  // shadcn-flavoured "we know your location" visual without a map dep.
  const dots = [];
  const rows = 3;
  const cols = 60;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // Concentrate dots roughly where landmasses sit on a Mercator strip.
      const x = c / cols;
      const inLand =
        (x > 0.05 && x < 0.27) || // Americas
        (x > 0.42 && x < 0.62) || // Europe / Africa
        (x > 0.65 && x < 0.85);   // Asia / Oceania
      if (!inLand) continue;
      // India sits around x ≈ 0.72 on this strip; mark that one
      const isIndia = x > 0.7 && x < 0.74 && r === 1;
      dots.push({ x, r, isIndia });
    }
  }
  return (
    <svg
      viewBox="0 0 600 32"
      preserveAspectRatio="xMidYMid slice"
      className="h-full w-full"
      aria-hidden
    >
      {dots.map((d, i) => (
        <circle
          key={i}
          cx={d.x * 600}
          cy={6 + d.r * 10}
          r={d.isIndia ? 2.4 : 1}
          fill={
            d.isIndia
              ? highlight
                ? "hsl(var(--success))"
                : "hsl(var(--destructive))"
              : "hsl(var(--muted-foreground) / 0.35)"
          }
        />
      ))}
    </svg>
  );
}

function ChecksSection({
  checks,
  flags,
}: {
  checks: Check[];
  flags: string[];
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Separator className="mb-4" />
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-1.5">
          <ListChecks className="h-3.5 w-3.5" />
          What we checked
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="mt-3 space-y-2.5">
          {checks.map((c) => (
            <CheckRow key={c.name} check={c} />
          ))}
          {flags.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Flags
              </div>
              <div className="flex flex-wrap gap-1.5">
                {flags.map((f) => (
                  <span
                    key={f}
                    className="rounded-md bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-border"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CheckRow({ check }: { check: Check }) {
  const tone =
    check.status === "pass"
      ? { Icon: CheckCircle2, color: "text-success" }
      : check.status === "warn"
        ? { Icon: AlertTriangle, color: "text-warning" }
        : check.status === "fail"
          ? { Icon: XCircle, color: "text-destructive" }
          : { Icon: AlertTriangle, color: "text-muted-foreground" };
  const { Icon, color } = tone;
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-hairline bg-card/50 px-3 py-2">
      <div className="flex min-w-0 items-start gap-2.5">
        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", color)} />
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">
            {CHECK_LABEL[check.name] ?? check.name}
          </div>
          {check.detail && (
            <div className="mt-0.5 truncate text-[12px] text-muted-foreground">
              {check.detail}
            </div>
          )}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-sm font-semibold text-foreground">
          {Math.round(check.score * 100)}%
        </div>
        <div
          className={cn(
            "text-[10px] font-semibold uppercase tracking-wider",
            color,
          )}
        >
          {check.status}
        </div>
      </div>
    </div>
  );
}
