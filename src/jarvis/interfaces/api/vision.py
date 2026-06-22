# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis.kernel.settings import settings
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

    if not settings.face_recognition_enabled:
        return {"recognized": True, "name": "disabled", "confidence": 1.0}

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

        res = FaceRecognizer().process(frame, force=True)
        return {
            "recognized": res.recognized,
            "name": res.name,
            "confidence": round(res.confidence, 2),
        }

    return await loop.run_in_executor(None, _capture_direct)


# Cache module-niveau pour /verify-face-frame : évite de recharger référence.jpg
# à chaque requête (face_recognition.face_encodings sur 1 image ≈ 100-300 ms).
_FRAME_RECOGNIZER: FaceRecognizer | None = None


def _get_or_init_frame_recognizer() -> FaceRecognizer | None:
    """Recognizer dédié à /verify-face-frame.

    Préfère le recognizer du daemon vision s'il est actif (mêmes embeddings,
    pas de double chargement). Sinon en instancie un local mis en cache.
    """
    global _FRAME_RECOGNIZER
    daemon_recognizer = get_face_recognizer()
    if daemon_recognizer is not None and daemon_recognizer._available:
        return daemon_recognizer
    if _FRAME_RECOGNIZER is None:
        _FRAME_RECOGNIZER = FaceRecognizer()
    return _FRAME_RECOGNIZER if _FRAME_RECOGNIZER._available else None


@router.post("/api/vision/verify-face-frame")
async def verify_face_frame(request: Request) -> dict:
    """Vérifie un visage à partir d'une frame envoyée par le client.

    Body : {"image_b64": "<JPEG base64 sans le prefix data:image/jpeg;base64,>"}

    Évite le conflit caméra entre le navigateur (qui détient le flux pour le
    scan visuel MediaPipe) et le backend qui sinon échouerait sur
    cv2.VideoCapture(0). La frame est passée au FaceRecognizer existant qui
    compare avec vision_data/faces/référence.jpg via face_recognition.
    """
    import asyncio
    import base64

    import numpy as np

    # FACE_RECOGNITION_ENABLED=false → on ne reconnaît pas, mais on ne bloque
    # pas le wake : verdict « pass » (l'animation de scan s'est jouée côté UI).
    if not settings.face_recognition_enabled:
        return {"recognized": True, "name": "disabled", "confidence": 1.0}

    try:
        import cv2
    except ImportError:
        return {"recognized": False, "name": "error_no_cv2", "confidence": 0.0}

    data = await request.json()
    img_b64 = data.get("image_b64", "").strip()
    if not img_b64:
        raise HTTPException(400, "image_b64 manquant")

    try:
        img_bytes = base64.b64decode(img_b64, validate=True)
    except Exception:
        return {"recognized": False, "name": "error_decode", "confidence": 0.0}

    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if frame is None:
        return {"recognized": False, "name": "error_decode", "confidence": 0.0}

    recognizer = _get_or_init_frame_recognizer()
    if recognizer is None:
        return {"recognized": False, "name": "error_no_recognizer", "confidence": 0.0}

    # process() est CPU-bound (face_recognition) → executor pour ne pas bloquer la boucle.
    # force=True : appel discret (1 frame), on contourne le frame-skip 1/4.
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: recognizer.process(frame, force=True))
    return {
        "recognized": res.recognized,
        "name": res.name,
        "confidence": round(res.confidence, 2),
    }


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
            f"{settings.display_name} est détecté devant la caméra "
            f"(confiance {body.confidence:.0%}). Mode normal actif."
        )
    return {"status": "ok"}
