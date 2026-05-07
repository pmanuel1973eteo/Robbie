#!/usr/bin/env python3
"""
robot_eyes.py — mirrors facial expressions on stylized robot eyes.
Uses MediaPipe FaceMesh landmarks for real-time expression detection.

Requirements:
    pip install opencv-python "mediapipe==0.10.14"
"""

import cv2
import math
import time
from typing import Optional, Tuple

import numpy as np
import mediapipe as mp

# ── Layout constants ─────────────────────────────────────────────────────────
WIN_W, WIN_H = 920, 580
EYE_W, EYE_H = 175, 115
EYE_CY       = WIN_H // 2 - 25
GAP          = 95
LEFT_CX      = WIN_W // 2 - GAP // 2 - EYE_W // 2
RIGHT_CX     = WIN_W // 2 + GAP // 2 + EYE_W // 2
MOUTH_CX     = WIN_W // 2
MOUTH_CY     = EYE_CY + 145
MOUTH_W      = 145
MOUTH_H      = 24

# ── Emotion profiles ─────────────────────────────────────────────────────────
#   brow  : vertical offset from rest (neg=raised, pos=lowered)
#   open  : eye openness fraction (0–1)
#   pupil : iris radius scale (0–1)
#   color : BGR accent color
#   smile : +1 smile / 0 flat / -1 frown
#   slant : >0 → inner brow DOWN (angry), <0 → inner brow UP (sad/surprise)
PROFILES = {
    "happy":    dict(brow=-14, open=0.55, pupil=0.76, color=(  0,215,155), smile= 1.0, slant= -5),
    "sad":      dict(brow=  5, open=0.42, pupil=0.62, color=(140, 70, 30), smile=-1.0, slant=-18),
    "angry":    dict(brow=  6, open=0.30, pupil=0.95, color=( 20, 20,210), smile=-0.7, slant= 22),
    "surprise": dict(brow=-25, open=1.00, pupil=1.00, color=(  0,200,255), smile= 0.3, slant=-12),
    "fear":     dict(brow=-18, open=0.90, pupil=0.48, color=(145,  0,190), smile=-0.2, slant=-15),
    "disgust":  dict(brow=  8, open=0.37, pupil=0.88, color=( 30,155, 30), smile=-0.8, slant= 10),
    "neutral":  dict(brow=  0, open=0.72, pupil=0.82, color=(  0,175,235), smile= 0.0, slant=  0),
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def lerp_c(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

def dim(color: tuple, factor: float) -> tuple:
    return tuple(int(min(255, c * factor)) for c in color)


# ── Expression detection from MediaPipe landmarks ────────────────────────────
# Key landmark indices (MediaPipe FaceMesh 468-point model)
_L_EYE_TOP, _L_EYE_BOT = 159, 145
_R_EYE_TOP, _R_EYE_BOT = 386, 374
_L_EYE_L, _L_EYE_R     = 33,  133
_R_EYE_L, _R_EYE_R     = 263, 362
_L_BROW_INNER           = 70
_R_BROW_INNER           = 300
_L_BROW_OUTER           = 46
_R_BROW_OUTER           = 276
_MOUTH_L, _MOUTH_R      = 61,  291   # left / right corners
_MOUTH_TOP, _MOUTH_BOT  = 13,  14    # center upper / lower lip
_FACE_TOP, _FACE_BOT    = 10,  152   # forehead / chin


class ExpressionDetector:
    """
    Derives an emotion label from MediaPipe FaceMesh landmarks.
    Calibrates to each user's neutral face over the first 60 frames.
    """

    CALIBRATION_FRAMES = 60

    def __init__(self):
        self._samples: list = []
        self._baseline: Optional[dict] = None
        self.emotion    = "neutral"
        self._smoothed  = dict(ear=0.25, mar=0.03, smile=0.0, brow=0.06)

    def _measures(self, lms, w: int, h: int) -> Optional[dict]:
        try:
            def y(i): return lms[i].y * h
            def x(i): return lms[i].x * w

            # Eye Aspect Ratio (EAR)
            ear_l = abs(y(_L_EYE_TOP) - y(_L_EYE_BOT)) / (abs(x(_L_EYE_L) - x(_L_EYE_R)) + 1e-6)
            ear_r = abs(y(_R_EYE_TOP) - y(_R_EYE_BOT)) / (abs(x(_R_EYE_L) - x(_R_EYE_R)) + 1e-6)
            ear   = (ear_l + ear_r) / 2

            # Mouth Aspect Ratio (MAR) — vertical / horizontal opening
            mar = abs(y(_MOUTH_TOP) - y(_MOUTH_BOT)) / (abs(x(_MOUTH_L) - x(_MOUTH_R)) + 1e-6)

            # Smile ratio: positive when corners are ABOVE mouth center
            face_h    = abs(y(_FACE_BOT) - y(_FACE_TOP)) + 1e-6
            corner_y  = (y(_MOUTH_L) + y(_MOUTH_R)) / 2
            center_y  = (y(_MOUTH_TOP) + y(_MOUTH_BOT)) / 2
            smile     = (center_y - corner_y) / face_h   # pos=smile, neg=frown

            # Brow raise ratio: distance from brow to eye top, normalised by face height
            brow_dist = (
                (y(_L_EYE_TOP) - y(_L_BROW_INNER)) +
                (y(_R_EYE_TOP) - y(_R_BROW_INNER))
            ) / 2 / face_h

            return dict(ear=ear, mar=mar, smile=smile, brow=brow_dist)
        except (IndexError, ZeroDivisionError):
            return None

    def _smooth(self, m: dict, alpha: float = 0.25):
        for k in m:
            self._smoothed[k] = lerp(self._smoothed[k], m[k], alpha)

    def update(self, lms, w: int, h: int) -> str:
        m = self._measures(lms, w, h)
        if m is None:
            return self.emotion

        # Calibration phase
        if self._baseline is None:
            self._samples.append(m)
            if len(self._samples) >= self.CALIBRATION_FRAMES:
                self._baseline = {
                    k: float(np.median([s[k] for s in self._samples]))
                    for k in m
                }
            return "neutral"

        self._smooth(m)
        s  = self._smoothed
        b  = self._baseline

        ear_delta  = s["ear"]   - b["ear"]     # >0 = wider than neutral
        mar_val    = s["mar"]                   # raw mouth openness
        smile_delta = s["smile"] - b["smile"]  # >0 = more smile than neutral
        brow_delta = s["brow"]  - b["brow"]    # >0 = brows higher than neutral

        # Decision (order matters — most distinctive first)
        if ear_delta > 0.06 and mar_val > 0.10:
            emotion = "surprise"
        elif smile_delta > 0.018:
            emotion = "happy"
        elif brow_delta < -0.018 and ear_delta < 0.0:
            emotion = "angry"
        elif smile_delta < -0.018 and brow_delta > 0.005:
            emotion = "sad"
        elif ear_delta < -0.06:
            emotion = "disgust"
        elif brow_delta > 0.025 and ear_delta > 0.03:
            emotion = "fear"
        else:
            emotion = "neutral"

        self.emotion = emotion
        return emotion

    @property
    def calibrating(self) -> bool:
        return self._baseline is None

    @property
    def calibration_progress(self) -> float:
        return min(1.0, len(self._samples) / self.CALIBRATION_FRAMES)


# ─────────────────────────────────────────────────────────────────────────────
class RobotFace:
    """Animated robot face that reacts to an emotion string."""

    def __init__(self):
        neutral = dict(PROFILES["neutral"])
        self._emotion = "neutral"
        self._state   = {k: float(v) if not isinstance(v, tuple) else v
                         for k, v in neutral.items()}
        self._target  = dict(neutral)
        # gaze
        self.look_x = 0.0;  self._tlook_x = 0.0
        self.look_y = 0.0;  self._tlook_y = 0.0
        # blink
        self._blink_open = 1.0
        self._blinking   = False
        self._blink_t    = 0.0
        self._next_blink = time.time() + 3.0
        self._prev_t     = time.time()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_emotion(self, name: str):
        name = name.lower()
        if name in PROFILES:
            self._emotion = name
            self._target  = dict(PROFILES[name])

    def set_gaze(self, x: float, y: float):
        self._tlook_x = max(-1.0, min(1.0, x))
        self._tlook_y = max(-1.0, min(1.0, y))

    def force_blink(self):
        if not self._blinking:
            self._blinking = True
            self._blink_t  = 0.0

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self):
        now = time.time()
        dt  = min(now - self._prev_t, 0.1)
        self._prev_t = now
        sp  = min(1.0, dt * 5.0)

        for k in ("brow", "open", "pupil", "smile", "slant"):
            self._state[k] = lerp(self._state[k], self._target[k], sp)
        self._state["color"] = lerp_c(self._state["color"], self._target["color"], sp)

        self.look_x = lerp(self.look_x, self._tlook_x, sp)
        self.look_y = lerp(self.look_y, self._tlook_y, sp)

        # auto-blink
        if not self._blinking and now >= self._next_blink:
            self._blinking = True
            self._blink_t  = 0.0
        if self._blinking:
            self._blink_t += dt * 9.0
            self._blink_open = max(0.0, 1.0 - math.sin(self._blink_t * math.pi))
            if self._blink_t >= 1.0:
                self._blinking   = False
                self._blink_open = 1.0
                self._next_blink = now + 2.5 + float(np.random.uniform(0, 3.0))

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, calibrating: bool = False,
               calib_progress: float = 0.0) -> np.ndarray:
        img = np.zeros((WIN_H, WIN_W, 3), np.uint8)
        col = self._state["color"]

        # grid background
        for x in range(0, WIN_W, 40):
            cv2.line(img, (x, 0), (x, WIN_H), (13, 13, 26), 1)
        for y in range(0, WIN_H, 40):
            cv2.line(img, (0, y), (WIN_W, y), (13, 13, 26), 1)

        # face panel
        cv2.rectangle(img, (45, 25), (WIN_W - 45, WIN_H - 25), (17, 17, 34), -1)
        cv2.rectangle(img, (45, 25), (WIN_W - 45, WIN_H - 25), dim(col, 0.45), 2)

        # corner rivets
        for rx, ry in [(68, 48), (WIN_W-68, 48), (68, WIN_H-48), (WIN_W-68, WIN_H-48)]:
            cv2.circle(img, (rx, ry), 6, (38, 38, 58), -1)
            cv2.circle(img, (rx, ry), 6, dim(col, 0.55), 1)
            cv2.circle(img, (rx, ry), 2, dim(col, 0.8), -1)

        self._draw_eye(img, LEFT_CX,  EYE_CY, -1)
        self._draw_eye(img, RIGHT_CX, EYE_CY,  1)
        self._draw_mouth(img)
        self._draw_nose(img)

        if calibrating:
            self._draw_calibration(img, calib_progress, col)
        else:
            label = self._emotion.upper()
            (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.putText(img, label, (WIN_W // 2 - tw // 2, WIN_H - 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, col, 2, cv2.LINE_AA)

        # subtle scanlines
        img[::3, :] = (img[::3, :] * 0.75).astype(np.uint8)
        return img

    # ── Internal drawing ──────────────────────────────────────────────────────

    def _glow_border(self, img, x1, y1, x2, y2, color, n=4):
        for i in range(n, 0, -1):
            c = dim(color, 0.07 * i)
            cv2.rectangle(img, (x1 - i*2, y1 - i*2), (x2 + i*2, y2 + i*2), c, 1)

    def _draw_eye(self, img: np.ndarray, cx: int, cy: int, side: int):
        s      = self._state
        color  = s["color"]
        ew, eh = EYE_W, EYE_H

        eff_open = s["open"] * self._blink_open
        vis_h    = max(2, int(eh * eff_open))
        top      = cy - vis_h // 2
        bot      = cy + vis_h // 2

        # socket housing
        cv2.rectangle(img, (cx - ew//2 - 7, cy - eh//2 - 7),
                           (cx + ew//2 + 7, cy + eh//2 + 7), (5, 5, 13), -1)
        cv2.rectangle(img, (cx - ew//2, cy - eh//2),
                           (cx + ew//2, cy + eh//2), (11, 11, 22), -1)
        self._glow_border(img, cx - ew//2, cy - eh//2, cx + ew//2, cy + eh//2, color)

        # iris / pupil
        lx = cx + int(self.look_x * ew * 0.18)
        ly = cy + int(self.look_y * eh * 0.14)
        ir = max(6, int(min(ew, eh) * 0.33 * s["pupil"]))

        if vis_h > 8:
            tmp = img.copy()
            cv2.circle(tmp, (lx, ly), ir + 9, dim(color, 0.18), -1)
            cv2.circle(tmp, (lx, ly), ir + 5, dim(color, 0.38), -1)
            cv2.circle(tmp, (lx, ly), ir, color, -1)
            cv2.circle(tmp, (lx, ly), int(ir * 0.68), dim(color, 0.50), 2)
            cv2.circle(tmp, (lx, ly), max(3, int(ir * 0.38)), (0, 0, 0), -1)
            cv2.circle(tmp, (lx - ir//4, ly - ir//4), max(2, ir//5), (185, 200, 255), -1)

            # clip iris to open area
            mask = np.zeros(img.shape[:2], np.uint8)
            ct   = max(cy - eh//2, top)
            cb   = min(cy + eh//2, bot)
            cv2.rectangle(mask, (cx - ew//2 + 2, ct), (cx + ew//2 - 2, cb), 255, -1)
            img[mask.astype(bool)] = tmp[mask.astype(bool)]

        # eyelids
        lid = (9, 9, 20)
        if top > cy - eh//2:
            cv2.rectangle(img, (cx - ew//2, cy - eh//2), (cx + ew//2, top - 1), lid, -1)
        if bot < cy + eh//2:
            cv2.rectangle(img, (cx - ew//2, bot + 1), (cx + ew//2, cy + eh//2), lid, -1)

        # frame border + corner brackets
        cv2.rectangle(img, (cx - ew//2 - 3, cy - eh//2 - 3),
                           (cx + ew//2 + 3, cy + eh//2 + 3), color, 2)
        bl = 16
        for (bx, by), (sx, sy) in [
            ((cx - ew//2 - 3, cy - eh//2 - 3), ( 1,  1)),
            ((cx + ew//2 + 3, cy - eh//2 - 3), (-1,  1)),
            ((cx - ew//2 - 3, cy + eh//2 + 3), ( 1, -1)),
            ((cx + ew//2 + 3, cy + eh//2 + 3), (-1, -1)),
        ]:
            cv2.line(img, (bx, by), (bx + sx * bl, by), color, 2)
            cv2.line(img, (bx, by), (bx, by + sy * bl), color, 2)

        # eyebrow
        # slant > 0 → inner brow DOWN (angry); slant < 0 → inner brow UP (sad)
        brow_y  = cy - eh//2 - 20 + int(s["brow"])
        inner_d = int(s["slant"] * 0.8)

        if side == -1:                          # left eye: inner = right end
            p1 = (cx - ew//2, brow_y - inner_d)
            p2 = (cx + ew//2, brow_y + inner_d)
        else:                                   # right eye: inner = left end
            p1 = (cx - ew//2, brow_y + inner_d)
            p2 = (cx + ew//2, brow_y - inner_d)

        cv2.line(img, (p1[0]+3, p1[1]+3), (p2[0]+3, p2[1]+3), (0, 0, 0), 14)
        cv2.line(img, p1, p2, color, 9)
        cv2.circle(img, p1, 5, color, -1)
        cv2.circle(img, p2, 5, color, -1)

    def _draw_nose(self, img: np.ndarray):
        color = self._state["color"]
        cx    = WIN_W // 2
        ny    = EYE_CY + EYE_H // 2 + 22
        cv2.circle(img, (cx, ny), 5, dim(color, 0.6), -1)
        cv2.circle(img, (cx, ny), 5, color, 1)

    def _draw_mouth(self, img: np.ndarray):
        s     = self._state
        color = s["color"]
        smile = s["smile"]
        cx    = MOUTH_CX

        cv2.rectangle(img,
                      (cx - MOUTH_W//2 - 7, MOUTH_CY - MOUTH_H//2 - 7),
                      (cx + MOUTH_W//2 + 7, MOUTH_CY + MOUTH_H//2 + 7),
                      (18, 18, 36), -1)
        cv2.rectangle(img,
                      (cx - MOUTH_W//2 - 4, MOUTH_CY - MOUTH_H//2 - 4),
                      (cx + MOUTH_W//2 + 4, MOUTH_CY + MOUTH_H//2 + 4),
                      color, 2)

        pts = []
        for i in range(41):
            t  = i / 40 - 0.5
            px = int(cx + t * MOUTH_W)
            py = int(MOUTH_CY - smile * MOUTH_H * 0.6 * (1 - 4*t*t))
            pts.append([px, py])
        pts = np.array(pts, np.int32)

        tmp  = img.copy()
        cv2.polylines(tmp, [pts], False, color, 4)
        mask = np.zeros(img.shape[:2], np.uint8)
        cv2.rectangle(mask,
                      (cx - MOUTH_W//2 - 3, MOUTH_CY - MOUTH_H//2 - 2),
                      (cx + MOUTH_W//2 + 3, MOUTH_CY + MOUTH_H//2 + 2),
                      255, -1)
        img[mask.astype(bool)] = tmp[mask.astype(bool)]

    def _draw_calibration(self, img: np.ndarray, progress: float, color: tuple):
        cx = WIN_W // 2
        # progress bar
        bar_w = 300
        bar_h = 12
        bx    = cx - bar_w // 2
        by    = WIN_H - 45
        cv2.rectangle(img, (bx - 2, by - 2), (bx + bar_w + 2, by + bar_h + 2),
                      dim(color, 0.4), 1)
        cv2.rectangle(img, (bx, by), (bx + int(bar_w * progress), by + bar_h),
                      color, -1)
        text = "CALIBRATING... keep a neutral face"
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(img, text, (cx - tw // 2, by - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


# ── Gaze estimation from iris landmarks ──────────────────────────────────────
def get_gaze(lms, img_w: int, img_h: int) -> Tuple[float, float]:
    """Normalised gaze (-1…1). Requires refine_landmarks=True (iris pts 468–477)."""
    try:
        def pt(i):
            return lms[i].x * img_w, lms[i].y * img_h

        lx_i, ly_i = pt(468)   # left iris center
        rx_i, ry_i = pt(473)   # right iris center

        l_ox, _ = pt(33);   l_ix, _ = pt(133)
        _, l_ty  = pt(159); _, l_by  = pt(145)
        r_ox, _ = pt(263);  r_ix, _ = pt(362)
        _, r_ty  = pt(386); _, r_by  = pt(374)

        l_gx = (lx_i - (l_ox + l_ix) / 2) / (abs(l_ix - l_ox) / 2 + 1e-6)
        r_gx = (rx_i - (r_ox + r_ix) / 2) / (abs(r_ix - r_ox) / 2 + 1e-6)
        gx   = (l_gx + r_gx) / 2

        l_gy = (ly_i - (l_ty + l_by) / 2) / (abs(l_ty - l_by) / 2 + 1e-6)
        r_gy = (ry_i - (r_ty + r_by) / 2) / (abs(r_ty - r_by) / 2 + 1e-6)
        gy   = (l_gy + r_gy) / 2

        return float(np.clip(gx * 2.5, -1, 1)), float(np.clip(gy * 2.5, -1, 1))
    except (IndexError, AttributeError):
        return 0.0, 0.0


# ─────────────────────────────────────────────────────────────────────────────
def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: cannot open webcam.")
        return

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    robot    = RobotFace()
    detector = ExpressionDetector()

    cv2.namedWindow("Robot Eyes", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Robot Eyes", WIN_W, WIN_H)

    ear_low_frames = 0
    prev_emo       = "neutral"

    print("Robot Eyes — keep a NEUTRAL face during calibration (~2 s).")
    print("Press Q or Esc to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame  = cv2.flip(frame, 1)
        h, w   = frame.shape[:2]
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = face_mesh.process(rgb)

        if result.multi_face_landmarks:
            lms = result.multi_face_landmarks[0].landmark

            # gaze
            gx, gy = get_gaze(lms, w, h)
            robot.set_gaze(gx, gy)

            # expression (landmark-based)
            emotion = detector.update(lms, w, h)
            if emotion != prev_emo:
                robot.set_emotion(emotion)
                prev_emo = emotion

            # user blink → robot blink  (EAR threshold)
            try:
                def lm_y(i): return lms[i].y * h
                def lm_x(i): return lms[i].x * w
                ear = ((abs(lm_y(159) - lm_y(145)) + abs(lm_y(386) - lm_y(374))) /
                       (abs(lm_x(33)  - lm_x(133)) + abs(lm_x(263) - lm_x(362)) + 1e-6))
                if ear < 0.09:
                    ear_low_frames += 1
                    if ear_low_frames == 2:
                        robot.force_blink()
                else:
                    ear_low_frames = 0
            except (IndexError, ZeroDivisionError):
                pass

        robot.update()
        canvas = robot.render(
            calibrating=detector.calibrating,
            calib_progress=detector.calibration_progress,
        )

        # webcam preview (bottom-right)
        ph, pw = 130, 174
        preview = cv2.resize(frame, (pw, ph))
        py0, px0 = WIN_H - ph - 10, WIN_W - pw - 10
        canvas[py0: py0 + ph, px0: px0 + pw] = preview
        col = robot._state["color"]
        cv2.rectangle(canvas, (px0 - 2, py0 - 2), (px0 + pw + 1, py0 + ph + 1), col, 1)
        cv2.putText(canvas, "CAM", (px0 + 4, py0 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1, cv2.LINE_AA)

        cv2.imshow("Robot Eyes", canvas)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    cap.release()
    face_mesh.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
