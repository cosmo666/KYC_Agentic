import { useRef, useState } from "react";
import { Camera, FileText, Lock, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const COPY: Record<
  string,
  { title: string; subtitle: string; reassurance: string }
> = {
  aadhaar: {
    title: "Upload your Aadhaar",
    subtitle: "Front side, well-lit, all corners visible.",
    reassurance:
      "We mask the first 8 digits before storing — only the last 4 are saved.",
  },
  pan: {
    title: "Upload your PAN",
    subtitle: "Front side, well-lit, all corners visible.",
    reassurance: "Used only for cross-verification with your Aadhaar.",
  },
};

export function DocumentUploadWidget({
  docType,
  accept,
  onFile,
  onOpenCamera,
  disabled,
}: {
  docType: string;
  accept: string[];
  onFile: (file: File) => void;
  onOpenCamera: () => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const copy = COPY[docType] ?? COPY.aadhaar;

  return (
    <Card className="overflow-hidden border-hairline shadow-md">
      <CardContent className="space-y-4 p-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-primary">
            <FileText className="h-3.5 w-3.5" />
            <span>{docType} document</span>
          </div>
          <h3 className="text-base font-semibold tracking-tight">
            {copy.title}
          </h3>
          <p className="text-sm text-muted-foreground">{copy.subtitle}</p>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files[0];
            if (f) onFile(f);
          }}
          className={cn(
            "rounded-xl border-2 border-dashed bg-muted/40 px-4 py-7 text-center transition-all",
            dragging
              ? "border-primary bg-primary/10 scale-[1.01]"
              : "border-border hover:border-primary/40 hover:bg-muted/70",
          )}
        >
          <div className="grid h-11 w-11 mx-auto place-items-center rounded-full bg-background ring-1 ring-border shadow-sm">
            <Upload
              className={cn(
                "h-5 w-5 transition-colors",
                dragging ? "text-primary" : "text-muted-foreground",
              )}
            />
          </div>
          <div className="mt-3 text-sm font-medium text-foreground">
            Drop file here
          </div>
          <div className="text-xs text-muted-foreground">
            JPG, PNG or PDF · up to 10 MB
          </div>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Button
              variant="default"
              size="sm"
              disabled={disabled}
              onClick={() => ref.current?.click()}
              className="active:scale-[0.98]"
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" /> Choose file
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={onOpenCamera}
              className="active:scale-[0.98]"
            >
              <Camera className="mr-1.5 h-3.5 w-3.5" /> Use camera
            </Button>
          </div>
          <input
            ref={ref}
            type="file"
            accept={accept.join(",")}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
          />
        </div>

        <div className="flex items-start gap-2 rounded-lg bg-success/5 px-3 py-2.5 text-[12px] leading-relaxed text-success ring-1 ring-success/15">
          <Lock className="mt-px h-3.5 w-3.5 shrink-0" />
          <span className="text-foreground/90">{copy.reassurance}</span>
        </div>
      </CardContent>
    </Card>
  );
}
