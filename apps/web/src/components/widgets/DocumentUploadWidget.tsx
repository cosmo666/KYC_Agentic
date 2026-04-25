import { useRef, useState } from "react";
import { Camera, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

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

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium capitalize">{docType} document</div>
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
          className={`rounded-md border-2 border-dashed p-6 text-center text-sm ${
            dragging ? "border-primary bg-primary/5" : "border-border"
          }`}
        >
          Drop your {docType} here, or
          <div className="mt-3 flex gap-2 justify-center">
            <Button
              variant="secondary"
              size="sm"
              disabled={disabled}
              onClick={() => ref.current?.click()}
            >
              <Upload className="h-4 w-4 mr-1.5" /> Choose file
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={disabled}
              onClick={onOpenCamera}
            >
              <Camera className="h-4 w-4 mr-1.5" /> Use camera
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
      </CardContent>
    </Card>
  );
}
