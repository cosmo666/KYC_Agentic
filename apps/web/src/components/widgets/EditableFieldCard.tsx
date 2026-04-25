import { Fragment, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Field = { name: string; label: string; value: string };

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
      <Card>
        <CardContent className="p-4 text-sm">
          <div className="font-medium mb-2 capitalize">
            {docType} — confirmed
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
            {fields.map((f) => (
              <Fragment key={f.name}>
                <dt>{f.label}</dt>
                <dd className="text-foreground">{values[f.name] || "—"}</dd>
              </Fragment>
            ))}
          </dl>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium capitalize">
          Review your {docType} details
        </div>
        {fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <Label htmlFor={`${docType}-${f.name}`}>{f.label}</Label>
            <Input
              id={`${docType}-${f.name}`}
              value={values[f.name] ?? ""}
              onChange={(e) =>
                setValues((v) => ({ ...v, [f.name]: e.target.value }))
              }
            />
          </div>
        ))}
        <div className="flex justify-end pt-2">
          <Button
            size="sm"
            onClick={() => {
              onConfirm(values);
              setConfirmed(true);
            }}
          >
            Confirm
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
