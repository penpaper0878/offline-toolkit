"""Faces: how many, where, and the points a passport photo is measured from.

YuNet (OpenCV's FaceDetectorYN, MIT) finds every face at any size. For the largest one, MediaPipe's face
landmark model (Apache-2.0) gives 478 points including the irises. It expects a square crop around the
face, turned so the eyes are level, about 1.5 times the face; the crop is made from YuNet's box first and
then from the model's own points, as MediaPipe does between video frames, until it settles.

Measurements, in the coordinates of the picture given:
- eyes: iris centres; eye tilt in degrees (positive = the right-hand eye in the picture is lower)
- chin: the lowest point of the face outline (landmark 152)
- crown: the top of the hair is measured on the person mask (passport.matte); the top of the skull is
  estimated from the eye-to-chin distance (adult heads have the eyes about halfway, a little lower), and
  never placed above the hair. Either can be corrected by hand in the editor.
- eye openness: eye aspect ratio from the lids (about 0.25-0.35 open, under 0.15 closed)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..design import assets

DETECTOR = "face_detection_yunet_2023mar.onnx"
LANDMARKS = "face_landmarks_detector.tflite"
CROP = 256
ANALYSE_SIDE = 1600          # faces are found on a copy at most this many px on the long side
SKULL_RATIO = 0.92           # top of skull to eye line, as a share of eye line to chin (adult average)

# MediaPipe face mesh indices ("left"/"right" as seen in the picture)
IRIS_L, IRIS_R = 468, 473
CHIN, FOREHEAD = 152, 10
EYE_L = (33, 160, 158, 133, 153, 144)          # outer, upper x2, inner, lower x2
EYE_R = (263, 387, 385, 362, 380, 373)
CHEEK_L, CHEEK_R = 234, 454
FACE_OVAL = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
             176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109)
EYE_L_RING = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)
EYE_R_RING = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466)
BROW_L = (70, 63, 105, 66, 107, 55, 65, 52, 53, 46)
BROW_R = (300, 293, 334, 296, 336, 285, 295, 282, 283, 276)
LIPS = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185)


class ModelMissing(RuntimeError):
    pass


@dataclass
class Face:
    box: tuple[float, float, float, float]      # YuNet box x, y, w, h
    score: float
    points: np.ndarray                          # (478, 2) float, picture coordinates
    presence: float                             # landmark model's face score (0-1)

    @property
    def eye_left(self) -> np.ndarray:
        return self.points[IRIS_L]

    @property
    def eye_right(self) -> np.ndarray:
        return self.points[IRIS_R]

    @property
    def eye_mid(self) -> np.ndarray:
        return (self.eye_left + self.eye_right) / 2

    @property
    def tilt(self) -> float:
        d = self.eye_right - self.eye_left
        return math.degrees(math.atan2(d[1], d[0]))

    @property
    def chin(self) -> np.ndarray:
        return self.points[CHIN]

    @property
    def up(self) -> np.ndarray:
        """Unit vector from the chin towards the top of the head (perpendicular to the eye line)."""
        d = self.eye_right - self.eye_left
        n = np.array([d[1], -d[0]]) / max(float(np.hypot(*d)), 1e-6)
        return n if n[1] < 0 else -n

    def skull_top(self, hair_top: np.ndarray | None = None) -> np.ndarray:
        """Estimated top of the skull; not above the top of the hair when that is known."""
        up = self.up
        ec = float(np.dot(self.eye_mid - self.chin, up))
        est = self.eye_mid + up * ec * SKULL_RATIO
        if hair_top is not None and np.dot(est - hair_top, up) > 0:
            return np.array(hair_top, dtype=float)
        return est

    def eye_openness(self) -> tuple[float, float]:
        def ear(idx):
            p = self.points
            p1, p2, p3, p4, p5, p6 = (p[i] for i in idx)
            return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2 * max(np.linalg.norm(p1 - p4), 1e-6)))
        return ear(EYE_L), ear(EYE_R)

    @property
    def width(self) -> float:
        return float(np.linalg.norm(self.points[CHEEK_R] - self.points[CHEEK_L]))

    def to_dict(self) -> dict:
        r = lambda v: [round(float(v[0]), 2), round(float(v[1]), 2)]  # noqa: E731
        return {"box": [round(float(v), 1) for v in self.box], "score": round(self.score, 3),
                "presence": round(self.presence, 3), "eyes": [r(self.eye_left), r(self.eye_right)],
                "chin": r(self.chin), "tilt": round(self.tilt, 2), "width": round(self.width, 1),
                "openness": [round(v, 3) for v in self.eye_openness()]}


@dataclass
class Faces:
    faces: list[Face] = field(default_factory=list)      # largest first
    others: int = 0                                      # faces found by YuNet but not measured

    @property
    def count(self) -> int:
        return len(self.faces) + self.others

    @property
    def main(self) -> Face | None:
        return self.faces[0] if self.faces else None


_detector = None
_landmarker = None


def _models():
    global _detector, _landmarker
    import cv2

    if _landmarker is None:
        det, lm = assets.model_path(DETECTOR), assets.model_path(LANDMARKS)
        if det is None or lm is None:
            raise ModelMissing("The face models are missing; run scripts/fetch_models.py (or reinstall the app).")
        _detector = cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.6, 0.3, 5000)
        # The classic engine returns every named output (the landmarks are not the graph's last output).
        _landmarker = cv2.dnn.readNetFromTFLite(str(lm), cv2.dnn.ENGINE_CLASSIC)
    return _detector, _landmarker


def _run_landmarks(rgb: np.ndarray, cx: float, cy: float, side: float, angle: float) -> tuple[np.ndarray, float]:
    import cv2

    _, net = _models()
    m = cv2.getRotationMatrix2D((float(cx), float(cy)), float(angle), CROP / max(side, 1.0))
    m[0, 2] += CROP / 2 - cx
    m[1, 2] += CROP / 2 - cy
    crop = cv2.warpAffine(rgb, m, (CROP, CROP), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    net.setInput(cv2.dnn.blobFromImage(crop.astype(np.float32) / 255.0))
    pts, flag, _ = net.forward(["Identity", "Identity_1", "Identity_2"])
    pts = pts.reshape(-1, 3)[:, :2].astype(np.float64)
    inv = cv2.invertAffineTransform(m)
    pts = np.c_[pts, np.ones(len(pts))] @ inv.T
    return pts, float(1 / (1 + math.exp(-float(flag.ravel()[0]))))


def _roi_from_points(pts: np.ndarray) -> tuple[float, float, float, float]:
    """Square crop 1.5x the face outline, turned to level the eye corners (MediaPipe's tracking ROI)."""
    import cv2

    a, b = pts[33], pts[263]
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    c = pts[:468].mean(0)
    rot = cv2.getRotationMatrix2D((float(c[0]), float(c[1])), angle, 1.0)
    rp = np.c_[pts[:468], np.ones(468)] @ rot.T
    lo, hi = rp.min(0), rp.max(0)
    centre = cv2.invertAffineTransform(rot) @ np.r_[(lo + hi) / 2, 1.0]
    return float(centre[0]), float(centre[1]), float(max(hi - lo) * 1.5), angle


def detect(rgb: np.ndarray, max_faces: int = 3) -> Faces:
    """Find the faces in an RGB picture and measure the largest `max_faces` of them."""
    import cv2

    det, _ = _models()
    h, w = rgb.shape[:2]
    k = min(1.0, ANALYSE_SIDE / max(h, w))
    small = cv2.resize(rgb, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA) if k < 1 else rgb
    det.setInputSize((small.shape[1], small.shape[0]))
    _, found = det.detect(np.ascontiguousarray(small[:, :, ::-1]))
    if found is None or len(found) == 0:
        return Faces()
    found = sorted(found, key=lambda f: -float(f[2] * f[3]))
    out = Faces(others=max(0, len(found) - max_faces))
    for f in found[:max_faces]:
        x, y, bw, bh = (float(v) / k for v in f[:4])
        le, re = f[4:6] / k, f[6:8] / k
        angle = math.degrees(math.atan2(re[1] - le[1], re[0] - le[0]))
        pts, presence = _run_landmarks(rgb, x + bw / 2, y + bh / 2, max(bw, bh) * 1.5, angle)
        for _ in range(4):
            prev = pts
            pts, presence = _run_landmarks(rgb, *_roi_from_points(pts))
            if float(np.abs(pts - prev).mean()) < 0.25 * max(1.0, max(h, w) / 1000):
                break
        out.faces.append(Face((x, y, bw, bh), float(f[14]), pts, presence))
    return out


def hair_top(alpha: np.ndarray, face: Face, threshold: float = 0.5) -> tuple[np.ndarray | None, bool]:
    """Top of the hair: walking up the middle of the face column (perpendicular to the eye line) from the
    forehead until no probe across the central half of the face is inside the person matte.
    Returns (point, cut): `cut` is True when the hair reaches the edge of the picture, so the real top is
    not in it. `alpha` is the person matte of the same picture (0..1 or 0..255)."""
    a = alpha.astype(np.float32)
    if a.max() > 1.5:
        a /= 255.0
    h, w = a.shape
    up = face.up
    side = np.array([-up[1], up[0]])
    half = face.width * 0.25
    start = face.points[FOREHEAD]
    step = max(0.5, face.width / 300)
    top = None
    for t in np.arange(0.0, face.width * 2.5, step):
        inside = hits = 0
        for o in np.linspace(-half, half, 9):
            p = start + up * t + side * o
            x, y = int(round(p[0])), int(round(p[1]))
            if 0 <= x < w and 0 <= y < h:
                inside += 1
                hits += a[y, x] >= threshold
        if inside == 0:
            return top, True
        if hits == 0:
            return top, False
        top = start + up * t
    return top, True
