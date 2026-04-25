import { Fragment, useState } from "react";
import { Check, FileText, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Field = { name: string; label: string; value: string };

const LOCKED_FIELDS = new Set(["aadhaar_number"]);

const MONO_FIELDS = new Set(["aadhaar_number", "pan_number"]);

export function EditableFieldCard({
  docType,
  fields,
  onConfirm,
}: {
  docType: string;
  fields: Field[];
  onConfirm: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.name, f.value])),
  );
  const [confirmed, setConfirmed] = useState(false);

  if (confirmed) {
    return (
      <Card className="border-hairline shadow-md">
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-success">
            <Check className="h-3.5 w-3.5" />
            <span>{docType} confirmed</span>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            {fields.map((f) => (
              <Fragment key={f.name}>
                <dt className="text-muted-foreground">{f.label}</dt>
                <dd
                  className={cn(
                    "font-medium text-foreground",
                    MONO_FIELDS.has(f.name) && "font-mono",
                  )}
                >
                  {values[f.name] || "—"}
                </dd>
              </Fragment>
            ))}
          </dl>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-hairline shadow-md">
      <CardContent className="space-y-4 p-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-primary">
            <FileText className="h-3.5 w-3.5" />
            <span>review {docType}</span>
          </div>
          <h3 className="text-base font-semibold tracking-tight">
            Confirm extracted details
          </h3>
          <p className="text-sm text-muted-foreground">
            Edit anything that doesn't look right, then confirm.
          </p>
        </div>

        <div className="space-y-3">
          {fields.map((f) => {
            const locked = LOCKED_FIELDS.has(f.name);
            const id = `${docType}-${f.name}`;
            return (
              <div key={f.name} className="space-y-1.5">
                <Label
                  htmlFor={id}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
                >
                  {f.label}
                  {locked && <Lock className="h-3 w-3" aria-label="Locked" />}
                </Label>
                <Input
                  id={id}
                  value={values[f.name] ?? ""}
                  readOnly={locked}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.name]: e.target.value }))
                  }
                  className={cn(
                    MONO_FIELDS.has(f.name) && "font-mono tracking-wide",
                    locked && "cursor-not-allowed bg-muted/60 text-muted-foreground",
                  )}
                />
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between gap-3 pt-1">
          <p className="text-[11px] text-muted-foreground">
            By confirming, you certify these details match your physical
            document.
          </p>
          <Button
            size="sm"
            onClick={() => {
              onConfirm(values);
              setConfirmed(true);
            }}
            className="shrink-0 active:scale-[0.98]"
          >
            <Check className="mr-1.5 h-3.5 w-3.5" />
            Confirm
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
