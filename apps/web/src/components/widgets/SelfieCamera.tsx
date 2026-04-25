import { useEffect, useRef, useState } from "react";
import { Camera, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function SelfieCamera({
  onCapture,
}: {
  onCapture: (blob: Blob) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (preview) return;
    let mounted = true;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" } })
      .then((s) => {
        if (!mounted) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
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
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium">Take a selfie</div>
        {error && (
          <div className="text-sm text-destructive">Camera error: {error}</div>
        )}
        {!preview ? (
          <>
            <video
              ref={videoRef}
              className="w-full rounded-md bg-black"
              autoPlay
              playsInline
              muted
            />
            <canvas ref={canvasRef} className="hidden" />
            <Button size="sm" onClick={capture} className="w-full">
              <Camera className="h-4 w-4 mr-1.5" /> Capture
            </Button>
          </>
        ) : (
          <>
            <img
              src={preview}
              alt="selfie preview"
              className="w-full rounded-md"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPreview(null)}
              className="w-full"
            >
              <RotateCcw className="h-4 w-4 mr-1.5" /> Retake
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
