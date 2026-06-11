from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis.providers.vision.daemon import get_face_recognizer
from jarvis.providers.vision.face_recognizer import FaceRecognizer

router = APIRouter()


# ── Vision endpoints ──────────────────────────────────────────────────────────


@router.post("/api/vision/verify-face")
async def verify_face() -> dict:
    """
    Retourne le résultat de la reconnaissance faciale.
    Utilise le FaceRecognizer du daemon vision si actif,
    sinon tente une capture directe (fallback).
    """
    import asyncio


    recognizer = get_face_recognizer()

    if recognizer is not None and recognizer._available:
        result = recognizer._last_result
        if result is None:
            await asyncio.sleep(0.6)
            result = recognizer._last_result
        if result is not None:
            return {
                "recognized": result.recognized,
                "name": result.name,
                "confidence": round(result.confidence, 2),
            }

    loop = asyncio.get_event_loop()

    def _capture_direct() -> dict:
        try:
            import cv2
        except ImportError:
            return {"recognized": False, "name": "error", "confidence": 0.0}
        cap = cv2.VideoCapture(0)
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return {"recognized": False, "name": "error", "confidence": 0.0}

        res = FaceRecognizer().process(frame)
        return {
            "recognized": res.recognized,
            "name": res.name,
            "confidence": round(res.confidence, 2),
        }

    return await loop.run_in_executor(None, _capture_direct)


@router.post("/api/vision/faces/add")
async def add_face(request: Request) -> dict:
    """Ajoute un visage de référence à chaud. Body: {name: str, path: str}"""
    data = await request.json()
    name = data.get("name", "").strip()
    path = data.get("path", "").strip()

    if not name or not path:
        raise HTTPException(400, "name et path requis")


    recognizer = get_face_recognizer()
    if recognizer is None:
        raise HTTPException(503, "FaceRecognizer non actif (FACE_RECOGNITION_ENABLED=false ?)")

    ok = recognizer.add_face(name, path)
    return {"success": ok, "name": name}


# ── Vision webhooks ───────────────────────────────────────────────────────────


class ObjectDetectedPayload(BaseModel):
    new_objects: list[str]
    all_objects: list[str] = []


@router.post("/api/webhooks/object_detected")
async def webhook_object_detected(body: ObjectDetectedPayload, request: Request) -> dict:
    """Reçoit les détections d'objets du daemon vision (YOLOv8n)."""
    if not body.new_objects:
        return {"status": "ignored"}

    notifications = request.app.state.notifications
    objects_str = ", ".join(body.new_objects)
    notifications.add(
        f"Nouveaux objets détectés devant la caméra : {objects_str}. "
        "Mentionne-le discrètement si c'est pertinent pour la conversation en cours, sinon ignore."
    )
    return {"status": "ok", "new_objects": body.new_objects}


class FaceRecognitionPayload(BaseModel):
    recognized: bool
    name: str = "unknown"
    confidence: float = 0.0


@router.post("/api/webhooks/face_recognition")
async def webhook_face_recognition(body: FaceRecognitionPayload, request: Request) -> dict:
    """Reçoit les changements d'état de reconnaissance faciale du daemon vision."""
    proactive = request.app.state.proactive_queue
    proactive.broadcast_event(
        {
            "type": "face_recognition",
            "recognized": body.recognized,
            "name": body.name,
            "confidence": body.confidence,
        }
    )
    if body.recognized:
        notifications = request.app.state.notifications
        notifications.add(
            f"Barth est détecté devant la caméra "
            f"(confiance {body.confidence:.0%}). Mode normal actif."
        )
    return {"status": "ok"}
