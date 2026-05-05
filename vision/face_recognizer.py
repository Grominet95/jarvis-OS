"""
Face recognition avec face_recognition (ageitgey/dlib).
Compare chaque frame webcam avec les photos de référence dans vision/faces/.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from loguru import logger


FACES_DIR = Path("vision/faces")


@dataclass
class RecognitionResult:
    recognized: bool        # True si Barth est reconnu
    confidence: float       # 0.0-1.0 (1 - distance)
    name: str               # "barth" ou "unknown"
    face_locations: list = field(default_factory=list)  # Coordonnées (1/4 scale)


class FaceRecognizer:
    """
    Compare les frames webcam avec les visages de référence.
    Charge toutes les images dans vision/faces/ au démarrage.
    """

    RECOGNITION_THRESHOLD = 0.45   # Distance max pour une correspondance (plus bas = plus strict)
    PROCESS_EVERY_N_FRAMES = 4     # Traiter 1 frame sur 4 pour les perfs

    def __init__(self):
        self._known_encodings: list[np.ndarray] = []
        self._known_names: list[str] = []
        self._frame_count = 0
        self._last_result: RecognitionResult | None = None
        self._available = self._load_known_faces()

    def _load_known_faces(self) -> bool:
        """Charge les photos de référence. Retourne False si face_recognition absent."""
        try:
            import face_recognition as fr
        except ImportError:
            logger.warning("FaceRecognizer: face_recognition non installé — désactivé")
            return False

        if not FACES_DIR.exists():
            logger.warning("FaceRecognizer: dossier vision/faces/ absent")
            return True

        for img_path in FACES_DIR.glob("*.jpg"):
            name = img_path.stem
            try:
                image = fr.load_image_file(str(img_path))
                encodings = fr.face_encodings(image)
                if encodings:
                    self._known_encodings.append(encodings[0])
                    self._known_names.append(name)
                    logger.info(f"FaceRecognizer: chargé {name}")
                else:
                    logger.warning(f"FaceRecognizer: aucun visage dans {img_path}")
            except Exception as e:
                logger.error(f"FaceRecognizer: erreur chargement {img_path}: {e}")

        logger.info(
            f"FaceRecognizer: {len(self._known_names)} visage(s) chargé(s): "
            f"{', '.join(self._known_names) or 'aucun'}"
        )
        return True

    def process(self, frame_bgr) -> RecognitionResult:
        """
        Analyse une frame BGR (OpenCV).
        Retourne le dernier résultat si pas le bon frame (optimisation).
        """
        _empty = RecognitionResult(recognized=False, confidence=0.0, name="unknown")

        if not self._available:
            return _empty

        self._frame_count += 1
        if self._frame_count % self.PROCESS_EVERY_N_FRAMES != 0:
            return self._last_result or _empty

        if not self._known_encodings:
            return RecognitionResult(recognized=False, confidence=0.0, name="no_reference")

        try:
            import cv2
            import face_recognition as fr

            small_frame = cv2.resize(frame_bgr, (0, 0), fx=0.25, fy=0.25)
            rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = fr.face_locations(rgb_small)

            if not face_locations:
                self._last_result = RecognitionResult(
                    recognized=False, confidence=0.0, name="unknown"
                )
                return self._last_result

            face_encodings = fr.face_encodings(rgb_small, face_locations)

            best_name = "unknown"
            best_confidence = 0.0
            recognized = False

            for encoding in face_encodings:
                distances = fr.face_distance(self._known_encodings, encoding)
                best_match_idx = int(np.argmin(distances))
                distance = distances[best_match_idx]
                confidence = 1.0 - distance

                if distance <= self.RECOGNITION_THRESHOLD:
                    best_name = self._known_names[best_match_idx]
                    best_confidence = confidence
                    recognized = True
                    break

            self._last_result = RecognitionResult(
                recognized=recognized,
                confidence=best_confidence,
                name=best_name,
                face_locations=face_locations,
            )
            return self._last_result

        except Exception as e:
            logger.error(f"FaceRecognizer.process error: {e}")
            return _empty

    def add_face(self, name: str, image_path: str) -> bool:
        """Ajouter un nouveau visage de référence à chaud."""
        try:
            import face_recognition as fr

            image = fr.load_image_file(image_path)
            encodings = fr.face_encodings(image)
            if encodings:
                self._known_encodings.append(encodings[0])
                self._known_names.append(name)
                dest = FACES_DIR / f"{name}.jpg"
                shutil.copy(image_path, dest)
                logger.info(f"FaceRecognizer: {name} ajouté")
                return True
            return False
        except Exception as e:
            logger.error(f"FaceRecognizer add_face error: {e}")
            return False
