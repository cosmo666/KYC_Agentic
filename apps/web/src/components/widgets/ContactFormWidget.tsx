import { useState, type FormEvent } from "react";
import { ArrowRight, Lock, Mail, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const DIGITS_RE = /\D+/g;
const MOBILE_RE = /^[6-9]\d{9}$/;

function normalizeMobile(raw: string): string {
  let digits = raw.replace(DIGITS_RE, "");
  if (digits.length > 10 && digits.startsWith("91")) digits = digits.slice(-10);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  return digits;
}

export type ContactField = {
  name: string;
  label: string;
  value: string;
  placeholder?: string | null;
  input_type?: string | null;
};

export function ContactFormWidget({
  fields,
  onSubmit,
}: {
  fields: ContactField[];
  onSubmit: (email: string, mobile: string) => Promise<void> | void;
}) {
  const initialEmail = fields.find((f) => f.name === "email")?.value ?? "";
  const initialMobile = fields.find((f) => f.name === "mobile")?.value ?? "";
  const [email, setEmail] = useState(initialEmail);
  const [mobile, setMobile] = useState(initialMobile);
  const [errors, setErrors] = useState<{
    email?: string;
    mobile?: string;
    form?: string;
  }>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (submitted) {
    return (
      <Card className="border-hairline shadow-md">
        <CardContent className="space-y-2 p-5">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-success">
            <Lock className="h-3.5 w-3.5" />
            <span>contact saved</span>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Email</dt>
            <dd className="font-medium text-foreground">{email}</dd>
            <dt className="text-muted-foreground">Mobile</dt>
            <dd className="font-mono font-medium text-foreground">{mobile}</dd>
          </dl>
        </CardContent>
      </Card>
    );
  }

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    const cleanMobile = normalizeMobile(mobile);
    const next: typeof errors = {};
    if (!EMAIL_RE.test(cleanEmail)) {
      next.email = "Enter a valid email address.";
    }
    if (cleanMobile.length !== 10) {
      next.mobile = `Mobile must be 10 digits (you entered ${cleanMobile.length}).`;
    } else if (!MOBILE_RE.test(cleanMobile)) {
      next.mobile = "Indian mobile must start with 6, 7, 8, or 9.";
    }
    if (Object.keys(next).length) {
      setErrors(next);
      return;
    }
    setErrors({});
    setSubmitting(true);
    try {
      await onSubmit(cleanEmail, cleanMobile);
      setSubmitted(true);
    } catch (err) {
      // Surface the server's verbatim message — the validators may catch
      // things the client missed (e.g. unicode-confusable characters).
      setErrors({ form: (err as Error).message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="overflow-hidden border-hairline shadow-md">
      <CardContent className="space-y-4 p-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-primary">
            <Mail className="h-3.5 w-3.5" />
            <span>get started</span>
          </div>
          <h3 className="text-base font-semibold tracking-tight">
            Your contact details
          </h3>
          <p className="text-sm text-muted-foreground">
            We'll send verification updates to your email and mobile.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3.5" noValidate>
          <div className="space-y-1.5">
            <Label
              htmlFor="contact-email"
              className="text-xs font-medium text-muted-foreground"
            >
              Email address
            </Label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="contact-email"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "contact-email-err" : undefined}
                className={cn(
                  "pl-9",
                  errors.email && "border-destructive focus-visible:ring-destructive",
                )}
              />
            </div>
            {errors.email && (
              <p id="contact-email-err" className="text-[12px] text-destructive">
                {errors.email}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label
              htmlFor="contact-mobile"
              className="text-xs font-medium text-muted-foreground"
            >
              Mobile number
            </Label>
            <div className="relative">
              <Phone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <span
                aria-hidden
                className="pointer-events-none absolute left-9 top-1/2 -translate-y-1/2 select-none font-mono text-sm font-medium text-foreground/70"
              >
                +91
              </span>
              <Input
                id="contact-mobile"
                type="tel"
                inputMode="tel"
                autoComplete="tel-national"
                placeholder="98765 43210"
                value={mobile}
                onChange={(e) => setMobile(e.target.value)}
                disabled={submitting}
                aria-invalid={!!errors.mobile}
                aria-describedby={
                  errors.mobile ? "contact-mobile-err" : "contact-mobile-help"
                }
                className={cn(
                  // Padding leaves room for the icon (left-3, 16px) + the
                  // "+91" prefix (left-9 + ~30px char width) + a small gap.
                  "pl-[4.5rem] font-mono tracking-wide",
                  errors.mobile &&
                    "border-destructive focus-visible:ring-destructive",
                )}
              />
            </div>
            {errors.mobile ? (
              <p id="contact-mobile-err" className="text-[12px] text-destructive">
                {errors.mobile}
              </p>
            ) : (
              <p id="contact-mobile-help" className="text-[11px] text-muted-foreground">
                10 digits, starting with 6, 7, 8, or 9.
              </p>
            )}
          </div>

          {errors.form && (
            <div
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] text-destructive"
            >
              {errors.form}
            </div>
          )}

          <Button
            type="submit"
            disabled={submitting}
            className="w-full active:scale-[0.98]"
          >
            {submitting ? (
              "Saving…"
            ) : (
              <>
                Continue
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </>
            )}
          </Button>

          <p className="text-[11px] text-muted-foreground">
            By continuing, you agree to our verification process. Your Aadhaar
            is masked before storage.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
