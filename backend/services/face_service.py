# backend/services/face_service.py

import os


def verify_faces(selfie_path: str, document_path: str) -> dict:
    """
    Compare a selfie with the photo on a KYC document.
    DeepFace is imported lazily to avoid startup crashes.
    """
    try:
        # Lazy import to avoid crashing the server on startup
        from deepface import DeepFace

        # Verify faces using DeepFace
        result = DeepFace.verify(
            img1_path=selfie_path,
            img2_path=document_path,
            model_name="VGG-Face",
            detector_backend="opencv",
            enforce_detection=False,
            distance_metric="cosine",
        )

        distance = result.get("distance", 1.0)
        threshold = result.get("threshold", 0.40)
        confidence = max(0, min(100, (1 - distance / threshold) * 100))

        return {
            "verified": result.get("verified", False),
            "distance": round(distance, 4),
            "threshold": round(threshold, 4),
            "confidence": round(confidence, 1),
            "model": result.get("model", "VGG-Face"),
            "faces_detected": True,
        }

    except ValueError as e:
        error_msg = str(e).lower()
        if "face" in error_msg and "detect" in error_msg:
            return {
                "verified": False,
                "distance": None,
                "threshold": None,
                "confidence": 0,
                "model": "VGG-Face",
                "faces_detected": False,
                "error": "Could not detect a face in one or both images. Please upload a clearer photo.",
            }
        return {
            "verified": False,
            "distance": None,
            "threshold": None,
            "confidence": 0,
            "model": "VGG-Face",
            "faces_detected": False,
            "error": f"Face verification error: {str(e)}",
        }

    except Exception as e:
        return {
            "verified": False,
            "distance": None,
            "threshold": None,
            "confidence": 0,
            "model": "VGG-Face",
            "faces_detected": False,
            "error": f"Face verification failed: {str(e)}",
        }
