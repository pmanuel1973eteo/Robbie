import { useCallback, useEffect, useRef, useState } from 'react';

const CALIBRATION_FRAMES  = 5;
const CALIBRATION_TIMEOUT = 15000;
const FETCH_TIMEOUT_MS    = 5000;

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function classifyEmotion(metrics, baseline, sensitivity = 1.0) {
  const { ear, mar, smile, brow } = metrics;
  const s = sensitivity;

  if (!baseline) return smile > 0.02 ? 'happy' : 'neutral';

  const earDelta   = ear   - baseline.ear;
  const smileDelta = smile - baseline.smile;
  const browDelta  = brow  - baseline.brow;

  if (earDelta   >  0.06 / s && mar > 0.10 / s)        return 'surprised';
  if (smileDelta >  0.015 / s)                          return 'happy';
  if (browDelta  < -0.018 / s && earDelta < 0.0)        return 'angry';
  if (smileDelta < -0.018 / s && browDelta > 0.005 / s) return 'sad';
  return 'neutral';
}

export default function useFaceEmotion({ sensitivityRef } = {}) {
  const [isCalibrating, setCalibrating] = useState(true);
  const [debugInfo,     setDebugInfo]   = useState('aguarda rosto…');

  const baselineRef  = useRef(null);
  const calibBuf     = useRef([]);
  const calibDoneRef = useRef(false);
  const busyRef      = useRef(false);

  const finishCalibration = useCallback(() => {
    if (calibDoneRef.current) return;
    calibDoneRef.current = true;
    if (calibBuf.current.length > 0) {
      const buf = calibBuf.current;
      baselineRef.current = {
        ear:   median(buf.map(m => m.ear)),
        mar:   median(buf.map(m => m.mar)),
        smile: median(buf.map(m => m.smile)),
        brow:  median(buf.map(m => m.brow)),
      };
    }
    setCalibrating(false);
    setDebugInfo('calibrado ✓');
  }, []);

  useEffect(() => {
    const t = setTimeout(finishCalibration, CALIBRATION_TIMEOUT);
    return () => clearTimeout(t);
  }, [finishCalibration]);

  const analyzeImage = useCallback(async (uri, serverUrl) => {
    if (!serverUrl || busyRef.current) return null;
    busyRef.current = true;

    try {
      const form = new FormData();
      form.append('image', { uri, name: 'frame.jpg', type: 'image/jpeg' });

      const ctrl = new AbortController();
      const tid  = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
      let res;
      try {
        res = await fetch(`${serverUrl}/emotion`, {
          method: 'POST',
          body:   form,
          signal: ctrl.signal,
        });
      } finally {
        clearTimeout(tid);
      }

      if (!res.ok) { setDebugInfo(`server ${res.status}`); return null; }

      const data = await res.json();
      if (!data.face) { setDebugInfo('no face'); return null; }

      const m = data.metrics;

      if (!calibDoneRef.current) {
        calibBuf.current.push(m);
        setDebugInfo(`calib ${calibBuf.current.length}/${CALIBRATION_FRAMES} ear=${m.ear.toFixed(3)}`);
        if (calibBuf.current.length >= CALIBRATION_FRAMES) finishCalibration();
        return 'neutral';
      }

      const emotion = classifyEmotion(m, baselineRef.current, sensitivityRef?.current ?? 1.0);
      const b = baselineRef.current;
      setDebugInfo(
        `ear Δ${(m.ear-(b?.ear??0)).toFixed(3)} smile Δ${(m.smile-(b?.smile??0)).toFixed(3)} → ${emotion}`
      );
      return emotion;
    } catch (err) {
      setDebugInfo(err.name === 'AbortError' ? 'timeout' : `err: ${err.message?.slice(0, 30)}`);
      return null;
    } finally {
      busyRef.current = false;
    }
  }, [finishCalibration]);

  return { isReady: true, isCalibrating, analyzeImage, debugInfo };
}
