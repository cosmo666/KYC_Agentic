from __future__ import annotations

from pathlib import Path


def verify_faces(selfie_path: str | Path, reference_path: str | Path) -> dict:
    """Wrap DeepFace.verify. Imported lazily — pulls TensorFlow at import time."""
    from deepface import DeepFace

    try:
        result = DeepFace.verify(
            img1_path=str(reference_path),
            img2_path=str(selfie_path),
            model_name="VGG-Face",
            detector_backend="opencv",
            distance_metric="cosine",
            enforce_detection=False,
        )
        distance = float(result.get("distance", 1.0))
        threshold = float(result.get("threshold", 0.4))
        verified = bool(result.get("verified", False))
        confidence = max(0.0, min(100.0, (1 - distance / threshold) * 100))
        return {
            "verified": verified,
            "distance": distance,
            "confidence": round(confidence, 2),
            "threshold": threshold,
            "faces_detected": True,
        }
    except ValueError as exc:
        # Usually "Face could not be detected"
        return {
            "verified": False,
            "distance": 1.0,
            "confidence": 0.0,
            "faces_detected": False,
            "error": str(exc),
        }


def warm() -> None:
    """Force-load VGG-Face weights (downloads ~580 MB on first run) so the
    first user-facing /capture doesn't pay the cold-start cost.

    Runs synchronously inside whoever calls it; in main.py we fire this
    on a background asyncio task at app startup.
    """
    import io

    import numpy as np
    from deepface import DeepFace
    from PIL import Image

    # 64x64 noise — tiny but valid; we set enforce_detection=False so DeepFace
    # tolerates the absence of a real face. Goal is to pull weights into RAM,
    # not to get a meaningful answer.
    img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    arr = np.array(Image.open(buf))
    try:
        DeepFace.verify(
            img1_path=arr,
            img2_path=arr,
            model_name="VGG-Face",
            detector_backend="opencv",
            distance_metric="cosine",
            enforce_detection=False,
        )
        DeepFace.analyze(
            img_path=arr,
            actions=["gender"],
            detector_backend="opencv",
            enforce_detection=False,
        )
    except Exception as exc:  # noqa: BLE001
        # Warmup is best-effort. If it fails (no internet at boot, etc.) the
        # real /capture call will retry the download lazily.
        print(f"[deepface] warmup failed: {exc!r}", flush=True)


def analyze_gender(selfie_path: str | Path) -> dict:
    from deepface import DeepFace

    try:
        res = DeepFace.analyze(
            img_path=str(selfie_path),
            actions=["gender"],
            detector_backend="opencv",
            enforce_detection=False,
        )
        if isinstance(res, list) and res:
            res = res[0]
        dominant = res.get("dominant_gender") or "unknown"
        return {"predicted_gender": dominant.lower(), "raw": res}
    except Exception as exc:
        return {"predicted_gender": None, "error": str(exc)}


def extract_largest_face(
    image_path: str | Path,
    out_path: str | Path | None = None,
) -> str | None:
    """Detect every face in `image_path`, save the LARGEST crop to `out_path`,
    and return the saved path. Returns None if no face is detected.

    Used to crop the photo region out of an Aadhaar scan so face verification
    runs against the photo only (instead of the whole card, which contains
    text, logos, the QR code, etc. that confuse VGG-Face).

    Tries detector backends in order of cost vs accuracy: opencv (fast,
    cheap), then retinaface (slower, more accurate) as fallback.
    """
    from deepface import DeepFace
    import numpy as np
    from PIL import Image

    image_path = Path(image_path)
    out_path = (
        Path(out_path)
        if out_path
        else image_path.with_name(f"{image_path.stem}_face{image_path.suffix or '.jpg'}")
    )

    for backend in ("opencv", "retinaface"):
        try:
            faces = DeepFace.extract_faces(
                img_path=str(image_path),
                detector_backend=backend,
                enforce_detection=True,  # we want a real detection, not the whole image
                align=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[deepface] extract_faces({backend}) failed: {exc!r}",
                flush=True,
            )
            continue
        if not faces:
            continue

        # Pick the largest face by facial_area width*height.
        def _area(f: dict) -> int:
            fa = f.get("facial_area") or {}
            return int(fa.get("w", 0)) * int(fa.get("h", 0))

        best = max(faces, key=_area)
        face_arr = best.get("face")
        if face_arr is None:
            continue
        # DeepFace returns the face as a normalised float array (0..1) — convert
        # back to uint8 so PIL can write it.
        arr = np.asarray(face_arr)
        if arr.dtype != np.uint8:
            arr = (arr * 255).clip(0, 255).astype(np.uint8)
        Image.fromarray(arr).save(str(out_path), quality=92)
        print(
            f"[deepface] cropped face from {image_path.name} -> {out_path.name} "
            f"via {backend}",
            flush=True,
        )
        return str(out_path)

    return None
