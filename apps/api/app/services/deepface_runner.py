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
