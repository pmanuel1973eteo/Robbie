#!/usr/bin/env python3
"""
robot_eyes2.py — cute robot face, light theme, fluffy oval eyes.
Same expression detection as robot_eyes.py; only rendering differs.
"""

import cv2
import json
import math
import os
import random
import subprocess
import threading
import time
from typing import Optional, Tuple

import numpy as np
import mediapipe as mp

# ── Layout ────────────────────────────────────────────────────────────────────
WIN_W, WIN_H = 920, 580
EYE_W, EYE_H = 170, 130
EYE_CY       = WIN_H // 2 - 30
GAP          = 110
LEFT_CX      = WIN_W // 2 - GAP // 2 - EYE_W // 2
RIGHT_CX     = WIN_W // 2 + GAP // 2 + EYE_W // 2
MOUTH_CX     = WIN_W // 2
MOUTH_CY     = EYE_CY + 155
MOUTH_W      = 128
MOUTH_H      = 30

# ── Theme ─────────────────────────────────────────────────────────────────────
BG_COL     = (230, 226, 218)
PANEL_COL  = (246, 243, 237)
GRID_COL   = (210, 205, 196)
SHADOW_COL = (178, 170, 155)
OUTLINE    = ( 48,  42,  36)
SCLERA_COL = (255, 254, 252)
EYELID_COL = (216, 208, 194)
BLUSH_COL  = (152, 172, 240)   # BGR soft pink

# ── Emotion profiles ──────────────────────────────────────────────────────────
PROFILES = {
    "happy":    dict(brow=-14, open=0.62, pupil=0.80, color=( 28,170, 60), smile= 1.0, slant= -5),
    "sad":      dict(brow=  5, open=0.42, pupil=0.60, color=(150, 78, 32), smile=-1.0, slant=-18),
    "angry":    dict(brow=  6, open=0.28, pupil=0.95, color=( 38, 38,208), smile=-0.7, slant= 22),
    "surprise": dict(brow=-25, open=1.00, pupil=1.00, color=(  0,155,225), smile= 0.3, slant=-12),
    "fear":     dict(brow=-18, open=0.90, pupil=0.48, color=(140, 18,190), smile=-0.2, slant=-15),
    "disgust":  dict(brow=  8, open=0.37, pupil=0.88, color=( 32,150, 38), smile=-0.8, slant= 10),
    "neutral":  dict(brow=  0, open=0.72, pupil=0.82, color=(  5,135,215), smile= 0.0, slant=  0),
}

# ── Landmark indices ──────────────────────────────────────────────────────────
_L_EYE_TOP, _L_EYE_BOT = 159, 145
_R_EYE_TOP, _R_EYE_BOT = 386, 374
_L_EYE_L,   _L_EYE_R   =  33, 133
_R_EYE_L,   _R_EYE_R   = 263, 362
_L_BROW_INNER           =  70
_R_BROW_INNER           = 300
_MOUTH_L,   _MOUTH_R    =  61, 291
_MOUTH_TOP, _MOUTH_BOT  =  13,  14
_FACE_TOP,  _FACE_BOT   =  10, 152

# ── Helpers ───────────────────────────────────────────────────────────────────
def lerp(a, b, t):
    return a + (b - a) * t

def lerp_c(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

def lighten(c, f):
    return tuple(int(v + (255 - v) * f) for v in c)

def darken(c, f):
    return tuple(int(v * (1 - f)) for v in c)

def rrect(img, x1, y1, x2, y2, r, color, thickness=-1):
    """Filled or outlined rounded rectangle."""
    r = min(r, max(0, (x2 - x1) // 2), max(0, (y2 - y1) // 2))
    if thickness < 0:
        cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), color, -1)
        for ex, ey in [(x1+r,y1+r),(x2-r,y1+r),(x1+r,y2-r),(x2-r,y2-r)]:
            cv2.circle(img, (ex, ey), r, color, -1)
    else:
        cv2.line(img, (x1+r, y1),  (x2-r, y1),  color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2,  y1+r), (x2,  y2-r), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2-r, y2),  (x1+r, y2),  color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1,  y2-r), (x1,  y1+r), color, thickness, cv2.LINE_AA)
        cv2.ellipse(img,(x1+r,y1+r),(r,r),0,180,270,color,thickness,cv2.LINE_AA)
        cv2.ellipse(img,(x2-r,y1+r),(r,r),0,270,360,color,thickness,cv2.LINE_AA)
        cv2.ellipse(img,(x2-r,y2-r),(r,r),0,  0, 90,color,thickness,cv2.LINE_AA)
        cv2.ellipse(img,(x1+r,y2-r),(r,r),0, 90,180,color,thickness,cv2.LINE_AA)


# ── Phrase engine (TTS via macOS `say`) ──────────────────────────────────────
class PhraseEngine:
    """
    Reads phrases.json and speaks emotion-triggered lines using the macOS
    `say` command in a background thread.  Never interrupts a phrase already
    playing; respects a per-emotion cooldown.
    """

    def __init__(self, json_path: str):
        self._voice     = "Joana"
        self._cooldown  = 8.0
        self._phrases: dict[str, list[str]] = {}
        self._greeting: list[str] = []
        self._proc: Optional[subprocess.Popen] = None
        self._lock      = threading.Lock()
        self._last_play = 0.0
        self.subtitle   = ""          # last spoken text (for on-screen display)
        self._sub_until = 0.0        # hide subtitle after this timestamp
        self._enabled   = False

        if not os.path.exists(json_path):
            print(f"[PhraseEngine] '{json_path}' not found — speech disabled.")
            return

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            self._voice    = data.get("voice", "Joana")
            self._cooldown = float(data.get("cooldown_seconds", 8))
            self._greeting = data.get("greeting", {}).get("phrases", [])
            for emotion, cfg in data.get("emotions", {}).items():
                self._phrases[emotion] = cfg.get("phrases", [])
            self._enabled = True
            print(f"[PhraseEngine] loaded '{json_path}', voice='{self._voice}'")
        except Exception as exc:
            print(f"[PhraseEngine] failed to load '{json_path}': {exc}")

    # ── Public ────────────────────────────────────────────────────────────────

    def greet(self):
        if self._greeting:
            self._speak(random.choice(self._greeting))

    def on_emotion(self, emotion: str):
        if not self._enabled:
            return
        if self._is_speaking():
            return
        now = time.time()
        if now - self._last_play < self._cooldown:
            return
        pool = self._phrases.get(emotion, [])
        if pool:
            self._speak(random.choice(pool))

    def current_subtitle(self) -> str:
        return self.subtitle if time.time() < self._sub_until else ""

    def close(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_speaking(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def _speak(self, text: str):
        self.subtitle   = text
        self._sub_until = time.time() + max(4.0, len(text) * 0.10)
        self._last_play = time.time()
        threading.Thread(target=self._run_say, args=(text,), daemon=True).start()

    def _run_say(self, text: str):
        cmd = ["say", "-v", self._voice, text]
        with self._lock:
            try:
                self._proc = subprocess.Popen(cmd)
            except FileNotFoundError:
                print("[PhraseEngine] `say` command not found.")
                return
        self._proc.wait()


# ── Expression detector (identical logic to robot_eyes.py) ───────────────────
class ExpressionDetector:
    CALIBRATION_FRAMES = 60

    def __init__(self):
        self._samples  = []
        self._baseline = None
        self.emotion   = "neutral"
        self._smoothed = dict(ear=0.25, mar=0.03, smile=0.0, brow=0.06)

    def _measures(self, lms, w, h):
        try:
            def y(i): return lms[i].y * h
            def x(i): return lms[i].x * w
            ear_l = abs(y(_L_EYE_TOP)-y(_L_EYE_BOT)) / (abs(x(_L_EYE_L)-x(_L_EYE_R))+1e-6)
            ear_r = abs(y(_R_EYE_TOP)-y(_R_EYE_BOT)) / (abs(x(_R_EYE_L)-x(_R_EYE_R))+1e-6)
            ear   = (ear_l + ear_r) / 2
            mar   = abs(y(_MOUTH_TOP)-y(_MOUTH_BOT)) / (abs(x(_MOUTH_L)-x(_MOUTH_R))+1e-6)
            face_h    = abs(y(_FACE_BOT)-y(_FACE_TOP)) + 1e-6
            corner_y  = (y(_MOUTH_L)+y(_MOUTH_R)) / 2
            center_y  = (y(_MOUTH_TOP)+y(_MOUTH_BOT)) / 2
            smile     = (center_y - corner_y) / face_h
            brow_dist = ((y(_L_EYE_TOP)-y(_L_BROW_INNER)) +
                         (y(_R_EYE_TOP)-y(_R_BROW_INNER))) / 2 / face_h
            return dict(ear=ear, mar=mar, smile=smile, brow=brow_dist)
        except (IndexError, ZeroDivisionError):
            return None

    def _smooth(self, m, alpha=0.25):
        for k in m:
            self._smoothed[k] = lerp(self._smoothed[k], m[k], alpha)

    def update(self, lms, w, h):
        m = self._measures(lms, w, h)
        if m is None:
            return self.emotion
        if self._baseline is None:
            self._samples.append(m)
            if len(self._samples) >= self.CALIBRATION_FRAMES:
                self._baseline = {k: float(np.median([s[k] for s in self._samples]))
                                  for k in m}
            return "neutral"
        self._smooth(m)
        s, b = self._smoothed, self._baseline
        ear_delta   = s["ear"]   - b["ear"]
        mar_val     = s["mar"]
        smile_delta = s["smile"] - b["smile"]
        brow_delta  = s["brow"]  - b["brow"]
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
    def calibrating(self):
        return self._baseline is None

    @property
    def calibration_progress(self):
        return min(1.0, len(self._samples) / self.CALIBRATION_FRAMES)


# ── Cute robot face ───────────────────────────────────────────────────────────
class RobotFace:
    def __init__(self):
        neutral       = dict(PROFILES["neutral"])
        self._emotion = "neutral"
        self._state   = {k: float(v) if not isinstance(v, tuple) else v
                         for k, v in neutral.items()}
        self._target  = dict(neutral)
        self.look_x   = 0.0;  self._tlook_x = 0.0
        self.look_y   = 0.0;  self._tlook_y = 0.0
        self._blink_open = 1.0
        self._blinking   = False
        self._blink_t    = 0.0
        self._next_blink = time.time() + 3.0
        self._prev_t     = time.time()

    def set_emotion(self, name):
        name = name.lower()
        if name in PROFILES:
            self._emotion = name
            self._target  = dict(PROFILES[name])

    def set_gaze(self, x, y):
        self._tlook_x = max(-1.0, min(1.0, x))
        self._tlook_y = max(-1.0, min(1.0, y))

    def force_blink(self):
        if not self._blinking:
            self._blinking = True
            self._blink_t  = 0.0

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
        if not self._blinking and now >= self._next_blink:
            self._blinking = True
            self._blink_t  = 0.0
        if self._blinking:
            self._blink_t   += dt * 9.0
            self._blink_open = max(0.0, 1.0 - math.sin(self._blink_t * math.pi))
            if self._blink_t >= 1.0:
                self._blinking   = False
                self._blink_open = 1.0
                self._next_blink = now + 2.5 + float(np.random.uniform(0, 3.0))

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, calibrating=False, calib_progress=0.0):
        img = np.zeros((WIN_H, WIN_W, 3), np.uint8)
        img[:] = BG_COL
        col = self._state["color"]

        # dot grid
        for gy in range(0, WIN_H, 28):
            for gx in range(0, WIN_W, 28):
                cv2.circle(img, (gx, gy), 1, GRID_COL, -1)

        # panel drop shadow
        rrect(img, 49, 27, WIN_W - 41, WIN_H - 17, 22, SHADOW_COL)
        # panel fill
        rrect(img, 45, 22, WIN_W - 45, WIN_H - 22, 22, PANEL_COL)
        # panel border
        rrect(img, 45, 22, WIN_W - 45, WIN_H - 22, 22, darken(col, 0.15), 3)

        # corner deco: small circles with a + sign
        for rx, ry in [(69, 46), (WIN_W-69, 46), (69, WIN_H-46), (WIN_W-69, WIN_H-46)]:
            cv2.circle(img, (rx, ry), 11, lighten(col, 0.65), -1)
            cv2.circle(img, (rx, ry), 11, darken(col, 0.12), 2)
            cv2.line(img, (rx-5, ry),   (rx+5, ry),   darken(col, 0.28), 2, cv2.LINE_AA)
            cv2.line(img, (rx,   ry-5), (rx,   ry+5), darken(col, 0.28), 2, cv2.LINE_AA)

        # blush cheeks
        self._draw_blush(img)

        self._draw_eye(img, LEFT_CX,  EYE_CY, -1)
        self._draw_eye(img, RIGHT_CX, EYE_CY,  1)
        self._draw_nose(img)
        self._draw_mouth(img)

        if calibrating:
            self._draw_calibration(img, calib_progress, col)
        else:
            label = self._emotion.upper()
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.62, 1)
            lx = WIN_W // 2 - tw // 2 - 14
            ly = WIN_H - 50
            rrect(img, lx, ly, lx + tw + 28, ly + th + 12, 8, lighten(col, 0.72))
            rrect(img, lx, ly, lx + tw + 28, ly + th + 12, 8, darken(col, 0.08), 2)
            cv2.putText(img, label, (WIN_W // 2 - tw // 2, ly + th + 4),
                        cv2.FONT_HERSHEY_DUPLEX, 0.62, darken(col, 0.30), 1, cv2.LINE_AA)

        return img

    # ── Internal drawing ──────────────────────────────────────────────────────

    def _draw_blush(self, img):
        if self._emotion in ("angry", "disgust"):
            return
        alpha = 0.20 if self._emotion == "happy" else 0.11
        tmp  = img.copy()
        lbx  = LEFT_CX  - EYE_W // 2 - 2
        rbx  = RIGHT_CX + EYE_W // 2 + 2
        by   = EYE_CY + EYE_H // 3 + 5
        for bx in (lbx, rbx):
            cv2.ellipse(tmp, (bx, by), (32, 18), 0, 0, 360, BLUSH_COL, -1)
        cv2.addWeighted(tmp, alpha, img, 1.0 - alpha, 0, img)

    def _draw_eye(self, img, cx, cy, side):
        s   = self._state
        col = s["color"]
        a, b = EYE_W // 2, EYE_H // 2

        eff_open = s["open"] * self._blink_open
        vis_h    = max(1, int(EYE_H * eff_open))
        top_clip = cy - vis_h // 2
        bot_clip = cy + vis_h // 2

        # drop shadow
        cv2.ellipse(img, (cx + 4, cy + 7), (a + 5, b + 5), 0, 0, 360, SHADOW_COL, -1)

        # sclera (white eye)
        cv2.ellipse(img, (cx, cy), (a, b), 0, 0, 360, SCLERA_COL, -1)

        # iris + pupil
        lx = cx + int(self.look_x * a * 0.22)
        ly = cy + int(self.look_y * b * 0.18)
        ir = max(8, int(min(a, b) * 0.40 * s["pupil"]))

        if vis_h > 8:
            tmp = img.copy()
            # soft glow halo
            cv2.circle(tmp, (lx, ly), ir + 8, lighten(col, 0.60), -1)
            # iris
            cv2.circle(tmp, (lx, ly), ir, col, -1)
            # inner ring
            cv2.circle(tmp, (lx, ly), int(ir * 0.62), darken(col, 0.22), 2)
            # pupil
            cv2.circle(tmp, (lx, ly), max(3, int(ir * 0.42)), (10, 10, 12), -1)
            # sparkle highlights
            cv2.circle(tmp, (lx - ir//4, ly - ir//4), max(3, ir//5),  (255,255,255), -1)
            cv2.circle(tmp, (lx + ir//5, ly - ir//5), max(2, ir//8),  (230,232,255), -1)

            # mask: ellipse shape clipped to open band
            mask = np.zeros(img.shape[:2], np.uint8)
            cv2.ellipse(mask, (cx, cy), (a - 2, b - 2), 0, 0, 360, 255, -1)
            mask[:max(0, top_clip), :] = 0
            mask[min(WIN_H, bot_clip + 1):, :] = 0
            img[mask.astype(bool)] = tmp[mask.astype(bool)]

        # upper eyelid overlay (blink / squint)
        if top_clip > cy - b:
            lid = np.zeros(img.shape[:2], np.uint8)
            cv2.ellipse(lid, (cx, cy), (a, b), 0, 0, 360, 255, -1)
            lid[max(0, top_clip):, :] = 0
            img[lid.astype(bool)] = EYELID_COL

        # lower eyelid overlay
        if bot_clip < cy + b:
            lid = np.zeros(img.shape[:2], np.uint8)
            cv2.ellipse(lid, (cx, cy), (a, b), 0, 0, 360, 255, -1)
            lid[:min(WIN_H, bot_clip + 1), :] = 0
            img[lid.astype(bool)] = EYELID_COL

        # eye outline
        cv2.ellipse(img, (cx, cy), (a, b), 0, 0, 360, OUTLINE, 2, cv2.LINE_AA)

        # eyelashes along upper arc
        if vis_h > EYE_H * 0.35:
            for t in (-0.62, -0.31, 0.0, 0.31, 0.62):
                under = max(0.0, 1 - t * t)
                lsh_x = cx + int(t * a)
                lsh_y = cy - int((b - 1) * math.sqrt(under))
                cv2.line(img, (lsh_x, lsh_y),
                         (lsh_x + int(t * 5), lsh_y - 9),
                         darken(col, 0.35), 2, cv2.LINE_AA)

        # eyebrow
        brow_y  = cy - b - 20 + int(s["brow"])
        inner_d = int(s["slant"] * 0.7)
        if side == -1:          # left eye: inner corner is on the right
            p1 = (cx - a + 12, brow_y - inner_d)
            p2 = (cx + a - 12, brow_y + inner_d)
        else:                   # right eye: inner corner is on the left
            p1 = (cx - a + 12, brow_y + inner_d)
            p2 = (cx + a - 12, brow_y - inner_d)

        cv2.line(img, (p1[0]+2, p1[1]+3), (p2[0]+2, p2[1]+3), SHADOW_COL, 14, cv2.LINE_AA)
        cv2.line(img, p1, p2, col, 11, cv2.LINE_AA)
        cv2.circle(img, p1, 5, col, -1)
        cv2.circle(img, p2, 5, col, -1)
        # brow highlight stripe
        cv2.line(img, (p1[0]+1, p1[1]-1), (p2[0]-1, p2[1]-1),
                 lighten(col, 0.45), 3, cv2.LINE_AA)

    def _draw_nose(self, img):
        col = self._state["color"]
        cx  = WIN_W // 2
        ny  = EYE_CY + EYE_H // 2 + 30
        for dx in (-10, 10):
            cv2.circle(img, (cx + dx, ny), 5, lighten(col, 0.45), -1)
            cv2.circle(img, (cx + dx, ny), 5, darken(col, 0.15),  2)

    def _draw_mouth(self, img):
        s     = self._state
        col   = s["color"]
        smile = s["smile"]
        cx    = MOUTH_CX

        rrect(img, cx - MOUTH_W//2 - 8, MOUTH_CY - MOUTH_H//2 - 8,
                   cx + MOUTH_W//2 + 8, MOUTH_CY + MOUTH_H//2 + 8,
                   10, lighten(col, 0.78))
        rrect(img, cx - MOUTH_W//2 - 8, MOUTH_CY - MOUTH_H//2 - 8,
                   cx + MOUTH_W//2 + 8, MOUTH_CY + MOUTH_H//2 + 8,
                   10, darken(col, 0.08), 2)

        pts = np.array([
            [int(cx + (i/40 - 0.5) * MOUTH_W),
             int(MOUTH_CY - smile * MOUTH_H * 0.65 * (1 - 4*(i/40 - 0.5)**2))]
            for i in range(41)
        ], np.int32)

        tmp  = img.copy()
        cv2.polylines(tmp, [pts], False, darken(col, 0.18), 5, cv2.LINE_AA)
        cv2.polylines(tmp, [pts], False, col,              3, cv2.LINE_AA)
        mask = np.zeros(img.shape[:2], np.uint8)
        cv2.rectangle(mask,
                      (cx - MOUTH_W//2 - 5, MOUTH_CY - MOUTH_H//2 - 3),
                      (cx + MOUTH_W//2 + 5, MOUTH_CY + MOUTH_H//2 + 3),
                      255, -1)
        img[mask.astype(bool)] = tmp[mask.astype(bool)]

    def _draw_calibration(self, img, progress, col):
        cx    = WIN_W // 2
        bar_w, bar_h = 300, 14
        bx    = cx - bar_w // 2
        by    = WIN_H - 52
        rrect(img, bx-3, by-3, bx+bar_w+3, by+bar_h+3, 6, lighten(col, 0.72))
        rrect(img, bx-3, by-3, bx+bar_w+3, by+bar_h+3, 6, darken(col, 0.08), 2)
        fill = max(0, int(bar_w * progress))
        if fill > 0:
            rrect(img, bx, by, bx + fill, by + bar_h, 5, col)
        text = "calibrating...  keep a neutral face"
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.44, 1)
        cv2.putText(img, text, (cx - tw//2, by - 10),
                    cv2.FONT_HERSHEY_DUPLEX, 0.44, darken(col, 0.28), 1, cv2.LINE_AA)


# ── Gaze estimation (identical to robot_eyes.py) ─────────────────────────────
def get_gaze(lms, img_w, img_h):
    try:
        def pt(i): return lms[i].x * img_w, lms[i].y * img_h
        lx_i, ly_i = pt(468); rx_i, ry_i = pt(473)
        l_ox, _ = pt(33);  l_ix, _ = pt(133)
        _, l_ty = pt(159); _, l_by = pt(145)
        r_ox, _ = pt(263); r_ix, _ = pt(362)
        _, r_ty = pt(386); _, r_by = pt(374)
        l_gx = (lx_i - (l_ox+l_ix)/2) / (abs(l_ix-l_ox)/2 + 1e-6)
        r_gx = (rx_i - (r_ox+r_ix)/2) / (abs(r_ix-r_ox)/2 + 1e-6)
        gx   = (l_gx + r_gx) / 2
        l_gy = (ly_i - (l_ty+l_by)/2) / (abs(l_ty-l_by)/2 + 1e-6)
        r_gy = (ry_i - (r_ty+r_by)/2) / (abs(r_ty-r_by)/2 + 1e-6)
        gy   = (l_gy + r_gy) / 2
        return float(np.clip(gx*2.5, -1, 1)), float(np.clip(gy*2.5, -1, 1))
    except (IndexError, AttributeError):
        return 0.0, 0.0


# ── Main ──────────────────────────────────────────────────────────────────────
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
    phrases  = PhraseEngine(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrases.json")
    )

    cv2.namedWindow("Robot Eyes 2", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Robot Eyes 2", WIN_W, WIN_H)

    ear_low_frames  = 0
    prev_emo        = "neutral"
    was_calibrating = True

    print("Robot Eyes 2 — keep a NEUTRAL face during calibration (~2 s).")
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

            gx, gy = get_gaze(lms, w, h)
            robot.set_gaze(gx, gy)

            emotion = detector.update(lms, w, h)
            if emotion != prev_emo:
                robot.set_emotion(emotion)
                phrases.on_emotion(emotion)
                prev_emo = emotion

            try:
                def lm_y(i): return lms[i].y * h
                def lm_x(i): return lms[i].x * w
                ear = ((abs(lm_y(159)-lm_y(145)) + abs(lm_y(386)-lm_y(374))) /
                       (abs(lm_x(33)-lm_x(133)) + abs(lm_x(263)-lm_x(362)) + 1e-6))
                if ear < 0.09:
                    ear_low_frames += 1
                    if ear_low_frames == 2:
                        robot.force_blink()
                else:
                    ear_low_frames = 0
            except (IndexError, ZeroDivisionError):
                pass

        # greeting once calibration finishes
        if was_calibrating and not detector.calibrating:
            phrases.greet()
            was_calibrating = False

        robot.update()
        canvas = robot.render(
            calibrating=detector.calibrating,
            calib_progress=detector.calibration_progress,
        )

        # subtitle (spoken phrase)
        sub = phrases.current_subtitle()
        if sub:
            col = robot._state["color"]
            (sw, sh), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_DUPLEX, 0.52, 1)
            sx = WIN_W // 2 - sw // 2
            sy = MOUTH_CY + MOUTH_H // 2 + 42
            rrect(canvas, sx - 12, sy - sh - 6, sx + sw + 12, sy + 8,
                  7, lighten(col, 0.82))
            rrect(canvas, sx - 12, sy - sh - 6, sx + sw + 12, sy + 8,
                  7, darken(col, 0.06), 1)
            cv2.putText(canvas, sub, (sx, sy),
                        cv2.FONT_HERSHEY_DUPLEX, 0.52, darken(col, 0.32), 1, cv2.LINE_AA)

        # webcam preview (bottom-right)
        ph, pw = 130, 174
        preview = cv2.resize(frame, (pw, ph))
        py0, px0 = WIN_H - ph - 10, WIN_W - pw - 10
        canvas[py0:py0+ph, px0:px0+pw] = preview
        col = robot._state["color"]
        rrect(canvas, px0-3, py0-3, px0+pw+2, py0+ph+2, 5, darken(col, 0.10), 2)
        cv2.putText(canvas, "CAM", (px0+5, py0+14),
                    cv2.FONT_HERSHEY_DUPLEX, 0.38, darken(col, 0.30), 1, cv2.LINE_AA)

        cv2.imshow("Robot Eyes 2", canvas)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    cap.release()
    face_mesh.close()
    phrases.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
