import { useCallback, useEffect, useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { Camera, Check, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Target = "aadhaar" | "pan";


async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const img = new Image();
  img.src = src;
  await new Promise<void>((resolve) => {
    img.onload = () => resolve();
  });
  const canvas = document.createElement("canvas");
  canvas.width = area.width;
  canvas.height = area.height;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(
    img,
    area.x,
    area.y,
    area.width,
    area.height,
    0,
    0,
    area.width,
    area.height,
  );
  return new Promise<Blob>((resolve) =>
    canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.92),
  );
}


export function CameraCaptureModal({
  open,
  target,
  onClose,
  onCropped,
}: {
  open: boolean;
  target: Target;
  onClose: () => void;
  onCropped: (blob: Blob) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        if (!mounted) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch((e) => console.error("Camera error:", e));
    return () => {
      mounted = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setSnapshot(null);
    };
  }, [open]);

  const grab = () => {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setSnapshot(URL.createObjectURL(blob));
        streamRef.current?.getTracks().forEach((t) => t.stop());
      },
      "image/jpeg",
      0.92,
    );
  };

  const retake = () => {
    setSnapshot(null);
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch((e) => console.error("Camera error:", e));
  };

  const use = useCallback(async () => {
    if (!snapshot || !area) return;
    const blob = await cropToBlob(snapshot, area);
    onCropped(blob);
    onClose();
  }, [snapshot, area, onCropped, onClose]);

  const onCropComplete = useCallback(
    (_: Area, px: Area) => setArea(px),
    [],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="font-medium capitalize">Capture {target}</div>
        <button onClick={onClose} aria-label="Close">
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="flex-1 relative bg-black">
        {!snapshot ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="h-full w-full object-contain"
          />
        ) : (
          <Cropper
            image={snapshot}
            crop={crop}
            zoom={zoom}
            aspect={undefined}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
          />
        )}
      </div>
      <div className="flex gap-2 p-3 border-t">
        {!snapshot ? (
          <Button className="flex-1" onClick={grab}>
            <Camera className="h-4 w-4 mr-1.5" /> Capture
          </Button>
        ) : (
          <>
            <Button variant="outline" onClick={retake} className="flex-1">
              <RotateCcw className="h-4 w-4 mr-1.5" /> Retake
            </Button>
            <Button onClick={use} className="flex-1">
              <Check className="h-4 w-4 mr-1.5" /> Use this
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
