import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Camera,
  Loader2,
  RotateCcw,
  ScanFace,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function SelfieCamera({
  onCapture,
  busy,
}: {
  onCapture: (blob: Blob) => void;
  busy?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (preview) return;
    let mounted = true;
    setReady(false);
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user", width: 720, height: 720 } })
      .then((s) => {
        if (!mounted) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          videoRef.current.onloadedmetadata = () => setReady(true);
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      mounted = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [preview]);

  const capture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setPreview(URL.createObjectURL(blob));
        streamRef.current?.getTracks().forEach((t) => t.stop());
        onCapture(blob);
      },
      "image/jpeg",
      0.92,
    );
  };

  return (
    <Card className="overflow-hidden border-hairline shadow-md">
      <CardContent className="space-y-4 p-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-primary">
            <ScanFace className="h-3.5 w-3.5" />
            <span>face verification</span>
          </div>
          <h3 className="text-base font-semibold tracking-tight">
            Take a selfie
          </h3>
          <p className="text-sm text-muted-foreground">
            Position your face inside the oval. Look straight at the camera.
          </p>
        </div>

        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">Camera unavailable</div>
              <div className="text-xs opacity-80">{error}</div>
            </div>
          </div>
        ) : !preview ? (
          <>
            <div className="relative mx-auto aspect-square w-full max-w-[320px] overflow-hidden rounded-2xl bg-black ring-1 ring-border shadow-md">
              <video
                ref={videoRef}
                className="h-full w-full scale-x-[-1] object-cover"
                autoPlay
                playsInline
                muted
              />
              <FaceGuide pulsing={ready} />
              {!ready && (
                <div className="absolute inset-0 grid place-items-center bg-black/40 text-xs text-white">
                  Starting camera…
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />
            <Button
              onClick={capture}
              disabled={!ready}
              className="w-full active:scale-[0.98]"
            >
              <Camera className="mr-1.5 h-4 w-4" /> Capture selfie
            </Button>
          </>
        ) : (
          <>
            <div className="relative mx-auto aspect-square w-full max-w-[320px] overflow-hidden rounded-2xl bg-black ring-1 ring-border shadow-md">
              <img
                src={preview}
                alt="Selfie preview"
                className="h-full w-full scale-x-[-1] object-cover"
              />
              {busy && (
                <div className="absolute inset-0 grid place-items-center bg-black/55 text-center text-white">
                  <div className="space-y-2">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                    <div className="text-sm font-medium">Verifying your face…</div>
                    <div className="text-[11px] opacity-80">
                      First verification may take up to a minute
                    </div>
                  </div>
                </div>
              )}
            </div>
            <Button
              variant="outline"
              onClick={() => setPreview(null)}
              disabled={busy}
              className="w-full active:scale-[0.98]"
            >
              <RotateCcw className="mr-1.5 h-4 w-4" /> Retake
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function FaceGuide({ pulsing }: { pulsing: boolean }) {
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <mask id="face-mask">
          <rect width="100" height="100" fill="white" />
          <ellipse cx="50" cy="50" rx="28" ry="36" fill="black" />
        </mask>
      </defs>
      <rect
        width="100"
        height="100"
        fill="black"
        opacity="0.45"
        mask="url(#face-mask)"
      />
      <ellipse
        cx="50"
        cy="50"
        rx="28"
        ry="36"
        fill="none"
        stroke="white"
        strokeOpacity={pulsing ? 0.85 : 0.4}
        strokeWidth="0.4"
        strokeDasharray="2 1.5"
        className={pulsing ? "[animation:pulse-ring_2s_ease-in-out_infinite]" : ""}
      />
    </svg>
  );
}
