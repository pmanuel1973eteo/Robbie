import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Animated,
  StyleSheet,
  StatusBar,
  Dimensions,
  Platform,
  Text,
  TouchableWithoutFeedback,
  AppState,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as NavigationBar from 'expo-navigation-bar';
import * as Speech from 'expo-speech';
import useFaceEmotion from './hooks/useFaceEmotion';
import SettingsPanel from './components/SettingsPanel';

const { width: SW, height: SH } = Dimensions.get('window');

const DEFAULT_PHRASES = {
  greeting:  ['Olá! Tudo bom?', 'Bom dia! Pronto para interagir!', 'Olá! Que bom ver-te!'],
  neutral:   ['Estou a observar-te com atenção.', 'Tudo tranquilo por aqui.', 'O que estás a pensar?'],
  happy:     ['Que alegria!', 'Estás muito bem disposto!', 'Boa disposição!', 'Que sorriso lindo!'],
  sad:       ['Ah, que tristeza...', 'Estás bem?', 'Posso ajudar com alguma coisa?', 'Espero que melhores em breve.'],
  angry:     ['Calma, respira fundo!', 'Tudo bem? Pareces zangado.', 'Não te preocupes tanto!'],
  surprised: ['Uau! Que surpresa!', 'Não esperava isso!', 'Oh! Que reação!'],
};
const DEFAULT_SETTINGS = {
  voiceEnabled:   true,
  emotionEnabled: true,
  showDebug:      true,
  sensitivity:    1.0,
  serverUrl:      'http://techcaresenior.eu:5001',
  headerTag:      'Eco-Digithon Portugal',
  phrases:        DEFAULT_PHRASES,
};
const SETTINGS_KEY   = 'robot_eyes_settings';
const SPEECH_COOLDOWN = 8000;

const EMOTION_LABELS = {
  neutral:   'Neutro',
  happy:     'Alegre',
  sad:       'Triste',
  angry:     'Zangado',
  surprised: 'Surpreendido',
  '—':       '—',
};

const EMOTION_COLORS = {
  neutral:   'rgba(0,238,255,0.90)',
  happy:     'rgba(136,255,170,0.95)',
  sad:       'rgba(80,140,255,0.95)',
  angry:     'rgba(255,80,50,0.95)',
  surprised: 'rgba(255,255,255,0.95)',
};

const MOOD_CONFIG = {
  neutral:   { topLid: 0.0,  botLid: 0.0,  scale: 1.00, color: null,      opac: 0,    smile: 1, flip:  1 },
  happy:     { topLid: 0.0,  botLid: 0.0,  scale: 1.12, color: '#88FFAA', opac: 0.08, smile: 1, flip:  1 },
  sad:       { topLid: 0.38, botLid: 0.0,  scale: 0.88, color: '#2244BB', opac: 0.22, smile: 1, flip: -1 },
  angry:     { topLid: 0.28, botLid: 0.22, scale: 0.80, color: '#FF2200', opac: 0.28, smile: 1, flip: -1 },
  surprised: { topLid: 0.0,  botLid: 0.0,  scale: 1.28, color: '#FFFFFF', opac: 0.12, smile: 1, flip:  1 },
};

// Responsive sizing
const BASE    = Math.min(SH * 0.32, 160);
const EYE_H   = BASE;
const EYE_W   = BASE * 0.86;
const EYE_R   = Math.min(EYE_W, EYE_H) * 0.48;
const EYE_GAP = EYE_W * 0.50;
const PUPIL   = EYE_W * 0.38;

const C = {
  bg:    '#000000',
  cyan:  '#00EEFF',
  glow1: 'rgba(0, 238, 255, 0.18)',
  glow2: 'rgba(0, 238, 255, 0.07)',
  pupil: '#001820',
};

const iosShadow = (r, o = 1) =>
  Platform.OS === 'ios'
    ? { shadowColor: C.cyan, shadowOffset: { width: 0, height: 0 }, shadowOpacity: o, shadowRadius: r }
    : {};

// ── Eye component ──────────────────────────────────────────────────────────────
function Eye({ eyelid, pupilX, pupilY, specularOpacity, scanY,
               botLidAnim, scaleY, overlayColor, overlayOpac }) {
  const topLidTranslate = eyelid.interpolate({
    inputRange: [0, 1], outputRange: [-EYE_H, 0],
  });
  const botLidTranslate = botLidAnim.interpolate({
    inputRange: [0, 1], outputRange: [EYE_H, 0],
  });

  return (
    <Animated.View style={[s.eyeOuter, { transform: [{ scaleY }] }]}>
      <View style={[s.halo, s.haloOuter, iosShadow(55, 0.20)]} />
      <View style={[s.halo, s.haloInner, iosShadow(28, 0.52)]} />
      <View style={[s.eyeBody, iosShadow(18, 1.0)]}>
        <View style={s.eyeClip}>
          <View style={s.rimBottom} />
          {/* Mood colour overlay */}
          <Animated.View
            style={[s.moodOverlay, { backgroundColor: overlayColor ?? 'transparent', opacity: overlayOpac }]}
          />
          <Animated.View style={[s.specular, { opacity: specularOpacity }]} />
          <Animated.View
            style={[s.pupilAnchor, { transform: [{ translateX: pupilX }, { translateY: pupilY }] }]}
          >
            <View style={s.pupil} />
            <View style={s.pupilGlint} />
          </Animated.View>
          <Animated.View style={[s.scanLine, { transform: [{ translateY: scanY }] }]} />
          {/* Top eyelid (blink + mood) */}
          <Animated.View style={[s.eyelid, { transform: [{ translateY: topLidTranslate }] }]} />
          {/* Bottom eyelid (angry squint) */}
          <Animated.View style={[s.eyelidBottom, { transform: [{ translateY: botLidTranslate }] }]} />
        </View>
      </View>
    </Animated.View>
  );
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  const alive    = useRef(true);

  // Base animations
  const breathY  = useRef(new Animated.Value(0)).current;
  const lEyelid  = useRef(new Animated.Value(0)).current;
  const rEyelid  = useRef(new Animated.Value(0)).current;
  const lPX      = useRef(new Animated.Value(0)).current;
  const lPY      = useRef(new Animated.Value(0)).current;
  const rPX      = useRef(new Animated.Value(0)).current;
  const rPY      = useRef(new Animated.Value(0)).current;
  const glanceX  = useRef(new Animated.Value(0)).current;
  const specular = useRef(new Animated.Value(1)).current;
  const scanY    = useRef(new Animated.Value(-EYE_H)).current;

  // Mood animations
  const topLidMood   = useRef(new Animated.Value(0)).current;
  const botLidAnim   = useRef(new Animated.Value(0)).current;
  const eyeScaleY    = useRef(new Animated.Value(1)).current;
  const overlayOpac  = useRef(new Animated.Value(0)).current;
  const smileOpac    = useRef(new Animated.Value(1)).current;
  const mouthFlipAnim = useRef(new Animated.Value(1)).current;
  const topLidBase  = useRef(0);
  const overlayColorRef = useRef(null);

  // Combined eyelid = max(topLidMood, blink)
  // We drive lEyelid directly from blink, and add topLidMood offset
  const effectiveLidL = Animated.add(lEyelid, topLidMood);
  const effectiveLidR = Animated.add(rEyelid, topLidMood);
  // Clamp to [0,1] via interpolation
  const clampedLidL = effectiveLidL.interpolate({ inputRange:[0,1,2], outputRange:[0,1,1], extrapolate:'clamp' });
  const clampedLidR = effectiveLidR.interpolate({ inputRange:[0,1,2], outputRange:[0,1,1], extrapolate:'clamp' });

  // Settings
  const [settings,        setSettings]        = useState(DEFAULT_SETTINGS);
  const [settingsVisible, setSettingsVisible] = useState(false);
  const settingsRef    = useRef(DEFAULT_SETTINGS);
  const sensitivityRef = useRef(DEFAULT_SETTINGS.sensitivity);
  const tapCount       = useRef(0);
  const tapTimer       = useRef(null);

  // App state (background/foreground)
  const appActive = useRef(true);

  const handleScreenTap = () => {
    tapCount.current += 1;
    clearTimeout(tapTimer.current);
    if (tapCount.current >= 3) {
      tapCount.current = 0;
      setSettingsVisible(true);
    } else {
      tapTimer.current = setTimeout(() => { tapCount.current = 0; }, 600);
    }
  };

  // TTS
  const [subtitle, setSubtitle] = useState('');
  const subtitleOpac  = useRef(new Animated.Value(0)).current;
  const lastSpokenAt  = useRef({});
  const subtitleTimer = useRef(null);
  const voiceOptions  = useRef({ language: 'pt-BR' });
  const talkAnim          = useRef(new Animated.Value(0)).current;
  const talkLoopRef       = useRef(null);
  const isSpeakingRemote  = useRef(false);

  // Camera
  const [permission, requestPermission] = useCameraPermissions();
  const hasCamPerm = permission?.granted ?? false;
  const [overlayColor, setOverlayColor] = useState(null);
  const [debugEmotion, setDebugEmotion] = useState('—');
  const cameraRef        = useRef(null);
  const pendingMood      = useRef('neutral');
  const pendingMoodCount = useRef(0);
  const currentMood      = useRef('neutral');

  // ML
  const { isReady, isCalibrating, analyzeImage, debugInfo } = useFaceEmotion({ sensitivityRef });

  // ── Load / save settings ─────────────────────────────────────────────────────
  useEffect(() => {
    AsyncStorage.getItem(SETTINGS_KEY).then((json) => {
      if (!json) return;
      try {
        const saved = JSON.parse(json);
        // merge with defaults so new keys are always present
        const merged = {
          ...DEFAULT_SETTINGS,
          ...saved,
          phrases: { ...DEFAULT_PHRASES, ...saved.phrases },
        };
        setSettings(merged);
        settingsRef.current = merged;
        sensitivityRef.current = merged.sensitivity;
      } catch (_) {}
    });
  }, []);

  const updateSettings = (next) => {
    setSettings(next);
    settingsRef.current = next;
    sensitivityRef.current = next.sensitivity;
    AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(next)).catch(() => {});
  };

  // ── Voice setup ─────────────────────────────────────────────────────────────
  useEffect(() => {
    Speech.getAvailableVoicesAsync().then((voices) => {
      const pt = voices.find(v => v.language?.startsWith('pt-PT'))
              ?? voices.find(v => v.language?.startsWith('pt'));
      if (pt) voiceOptions.current = { voice: pt.identifier };
    }).catch(() => {});
  }, []);

  // ── Mood transition ──────────────────────────────────────────────────────────
  const transitionToMood = (mood) => {
    const cfg = MOOD_CONFIG[mood] ?? MOOD_CONFIG.neutral;
    topLidBase.current = cfg.topLid;

    // Swap overlay colour with a quick fade-through-black
    Animated.sequence([
      Animated.timing(overlayOpac, { toValue: 0, duration: 150, useNativeDriver: true }),
    ]).start(() => {
      setOverlayColor(cfg.color);
      Animated.parallel([
        Animated.timing(topLidMood,   { toValue: cfg.topLid, duration: 600, useNativeDriver: true }),
        Animated.timing(botLidAnim,   { toValue: cfg.botLid, duration: 600, useNativeDriver: true }),
        Animated.timing(eyeScaleY,    { toValue: cfg.scale,  duration: 500, useNativeDriver: true }),
        Animated.timing(smileOpac,    { toValue: cfg.smile,  duration: 400, useNativeDriver: true }),
        Animated.timing(overlayOpac,  { toValue: cfg.opac,   duration: 400, useNativeDriver: true }),
        Animated.timing(mouthFlipAnim, { toValue: cfg.flip,  duration: 500, useNativeDriver: true }),
      ]).start();
    });
  };

  // ── Animação de boca ─────────────────────────────────────────────────────────
  const startTalking = () => {
    talkLoopRef.current?.stop();
    talkLoopRef.current = Animated.loop(
      Animated.sequence([
        Animated.timing(talkAnim, { toValue: 1,   duration: 110, useNativeDriver: true }),
        Animated.timing(talkAnim, { toValue: 0.3, duration: 90,  useNativeDriver: true }),
        Animated.timing(talkAnim, { toValue: 0.8, duration: 100, useNativeDriver: true }),
        Animated.timing(talkAnim, { toValue: 0,   duration: 120, useNativeDriver: true }),
      ])
    );
    talkLoopRef.current.start();
  };

  const stopTalking = () => {
    talkLoopRef.current?.stop();
    talkLoopRef.current = null;
    Animated.timing(talkAnim, { toValue: 0, duration: 200, useNativeDriver: true }).start();
  };

  // ── TTS ──────────────────────────────────────────────────────────────────────
  const speakMood = (mood) => {
    if (!settingsRef.current.voiceEnabled) return;
    if (isSpeakingRemote.current) return;
    const now  = Date.now();
    if ((now - (lastSpokenAt.current[mood] ?? 0)) < SPEECH_COOLDOWN) return;
    const pool   = settingsRef.current.phrases[mood]?.filter(Boolean);
    if (!pool?.length) return;
    const phrase = pool[Math.floor(Math.random() * pool.length)];
    lastSpokenAt.current[mood] = now;

    setSubtitle(phrase);
    Animated.timing(subtitleOpac, { toValue: 1, duration: 300, useNativeDriver: true }).start();

    const hide = () => {
      clearTimeout(subtitleTimer.current);
      stopTalking();
      Animated.timing(subtitleOpac, { toValue: 0, duration: 800, useNativeDriver: true }).start();
    };
    Speech.stop();
    Speech.speak(phrase, { ...voiceOptions.current, rate: 0.88, pitch: 1.05,
      onStart: startTalking,
      onDone: hide, onStopped: hide, onError: hide });
    subtitleTimer.current = setTimeout(hide, phrase.length * 90 + 1500);
  };

  // ── AppState (pausar ML em segundo plano) ────────────────────────────────────
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      appActive.current = state === 'active';
    });
    return () => sub.remove();
  }, []);

  // ── Remote message polling ───────────────────────────────────────────────────
  useEffect(() => {
    if (!settings.serverUrl) return;
    const interval = setInterval(async () => {
      if (!alive.current || !appActive.current) return;
      const url = settingsRef.current.serverUrl;
      if (!url) return;
      try {
        const ctrl = new AbortController();
        const tid  = setTimeout(() => ctrl.abort(), 3000);
        let res;
        try { res = await fetch(`${url}/message`, { signal: ctrl.signal }); }
        finally { clearTimeout(tid); }
        if (!res.ok) return;
        const data = await res.json();
        if (!data.message) return;
        const text = data.message;
        isSpeakingRemote.current = true;
        setSubtitle(text);
        Animated.timing(subtitleOpac, { toValue: 1, duration: 300, useNativeDriver: true }).start();
        const hide = () => {
          isSpeakingRemote.current = false;
          clearTimeout(subtitleTimer.current);
          stopTalking();
          Animated.timing(subtitleOpac, { toValue: 0, duration: 800, useNativeDriver: true }).start();
        };
        if (settingsRef.current.voiceEnabled) {
          Speech.stop();
          Speech.speak(text, { ...voiceOptions.current, rate: 0.88, pitch: 1.05,
            onStart: startTalking, onDone: hide, onStopped: hide, onError: hide });
        }
        subtitleTimer.current = setTimeout(hide, text.length * 90 + 1500);
      } catch (_) {}
    }, 3000);
    return () => clearInterval(interval);
  }, [settings.serverUrl]);

  // ── Reset to neutral when emotion recognition is turned off ──────────────────
  useEffect(() => {
    if (!settings.emotionEnabled) {
      currentMood.current      = 'neutral';
      pendingMood.current      = 'neutral';
      pendingMoodCount.current = 0;
      transitionToMood('neutral');
    }
  }, [settings.emotionEnabled]);

  // ── Camera permission ────────────────────────────────────────────────────────
  useEffect(() => {
    if (permission && !permission.granted && permission.canAskAgain) {
      requestPermission();
    }
  }, [permission]);

  // ── Camera capture loop ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!hasCamPerm) return;
    const interval = setInterval(async () => {
      if (!alive.current || !appActive.current) return;
      if (!settingsRef.current.emotionEnabled) return;
      if (!settingsRef.current.serverUrl) return;
      if (!cameraRef.current) return;
      try {
        const photo = await cameraRef.current.takePictureAsync({
          quality: 0.4, base64: false, shutterSound: false, exif: false,
        });
        const detected = await analyzeImage(photo.uri, settingsRef.current.serverUrl);
        if (detected === null) return;
        setDebugEmotion(detected);
        if (detected !== pendingMood.current) {
          pendingMood.current      = detected;
          pendingMoodCount.current = 1;
        } else {
          pendingMoodCount.current += 1;
          if (pendingMoodCount.current >= 2 && detected !== currentMood.current) {
            currentMood.current      = detected;
            pendingMoodCount.current = 0;
            transitionToMood(detected);
            speakMood(detected);
            fetch(`${settingsRef.current.serverUrl}/log`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ emotion: detected }),
            }).catch(() => {});
          }
        }
      } catch (_) {}
    }, 1500);
    return () => clearInterval(interval);
  }, [hasCamPerm, analyzeImage]);

  // ── Animations main loop ─────────────────────────────────────────────────────
  useEffect(() => {
    alive.current = true;

    if (Platform.OS === 'android') {
      NavigationBar.setVisibilityAsync('hidden');
    }

    const breathLoop = Animated.loop(Animated.sequence([
      Animated.timing(breathY, { toValue: -11, duration: 2700, useNativeDriver: true }),
      Animated.timing(breathY, { toValue: 0,   duration: 2700, useNativeDriver: true }),
    ]));
    breathLoop.start();

    const specLoop = Animated.loop(Animated.sequence([
      Animated.timing(specular, { toValue: 0.50, duration: 3400, useNativeDriver: true }),
      Animated.timing(specular, { toValue: 1.0,  duration: 3400, useNativeDriver: true }),
    ]));
    specLoop.start();

    const scanLoop = Animated.loop(Animated.sequence([
      Animated.timing(scanY, { toValue: EYE_H * 1.1, duration: 3200, useNativeDriver: true }),
      Animated.timing(scanY, { toValue: -EYE_H,      duration: 0,    useNativeDriver: true }),
      Animated.delay(1800),
    ]));
    scanLoop.start();

    let blinkT;
    const blink = () => {
      if (!alive.current) return;
      const base   = topLidBase.current;
      const lively = !settingsRef.current.emotionEnabled;
      const interval = base > 0.2
        ? 8000 + Math.random() * 5000              // angry: raro
        : lively
        ? 1000 + Math.random() * 1500              // vivacious
        : 3000 + Math.random() * 4000;             // normal
      blinkT = setTimeout(() => {
        Animated.parallel([
          Animated.sequence([
            Animated.timing(lEyelid, { toValue: 1 - base, duration: 65,  useNativeDriver: true }),
            Animated.timing(lEyelid, { toValue: 0,        duration: 105, useNativeDriver: true }),
          ]),
          Animated.sequence([
            Animated.timing(rEyelid, { toValue: 1 - base, duration: 65,  useNativeDriver: true }),
            Animated.timing(rEyelid, { toValue: 0,        duration: 105, useNativeDriver: true }),
          ]),
        ]).start(blink);
      }, interval);
    };
    blink();

    let pupilT;
    const drift = () => {
      if (!alive.current) return;
      const lively = !settingsRef.current.emotionEnabled;
      const mX  = EYE_W * (lively ? 0.23 : 0.16);
      const mY  = EYE_H * (lively ? 0.19 : 0.13);
      const dur = lively ? 500 + Math.random() * 800 : 900 + Math.random() * 1600;
      Animated.parallel([
        Animated.timing(lPX, { toValue: (Math.random()-.5)*2*mX, duration: dur, useNativeDriver: true }),
        Animated.timing(lPY, { toValue: (Math.random()-.5)*2*mY, duration: dur, useNativeDriver: true }),
        Animated.timing(rPX, { toValue: (Math.random()-.5)*2*mX, duration: dur, useNativeDriver: true }),
        Animated.timing(rPY, { toValue: (Math.random()-.5)*2*mY, duration: dur, useNativeDriver: true }),
      ]).start(() => { pupilT = setTimeout(drift, lively ? 80 + Math.random() * 150 : 150 + Math.random() * 350); });
    };
    drift();

    let glanceT;
    const glance = () => {
      if (!alive.current) return;
      const lively = !settingsRef.current.emotionEnabled;
      glanceT = setTimeout(() => {
        const dir = Math.random() > 0.5 ? 1 : -1;
        Animated.sequence([
          Animated.timing(glanceX, { toValue: dir * (38 + Math.random()*24), duration: 155, useNativeDriver: true }),
          Animated.delay(550 + Math.random()*500),
          Animated.timing(glanceX, { toValue: 0, duration: 210, useNativeDriver: true }),
        ]).start(glance);
      }, lively ? 1500 + Math.random()*2000 : 5000 + Math.random()*5000);
    };
    glance();

    const greetT    = setTimeout(() => speakMood('greeting'), 2000);
    const periodicT = setInterval(() => speakMood('neutral'), 45000);

    return () => {
      alive.current = false;
      breathLoop.stop(); specLoop.stop(); scanLoop.stop();
      clearTimeout(blinkT); clearTimeout(pupilT); clearTimeout(glanceT);
      clearTimeout(greetT); clearTimeout(subtitleTimer.current);
      clearInterval(periodicT);
      talkLoopRef.current?.stop();
      Speech.stop();
    };
  }, []);

  const smileW     = EYE_W * 2 + EYE_GAP;
  const smileArcH  = smileW * 0.60;
  const smileClipH = smileArcH * 0.34;
  const smileTotal = EYE_W * 0.20 + smileClipH;
  const talkScaleY     = talkAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.65] });
  const talkTranslateY = talkAnim.interpolate({ inputRange: [0, 1], outputRange: [0, smileClipH * 0.325] });

  const statusText = !settings.serverUrl && settings.emotionEnabled
    ? 'Sem servidor configurado'
    : isCalibrating
    ? 'Mantém rosto neutro para calibrar...'
    : null;

  return (
    <TouchableWithoutFeedback onPress={handleScreenTap}>
    <View style={s.root}>
      <StatusBar hidden />
      <View style={[s.bgHalo, iosShadow(160, 0.05)]} />

      {/* Câmara frontal oculta para deteção */}
      {hasCamPerm && (
        <CameraView
          ref={cameraRef}
          style={s.hiddenCamera}
          facing="front"
          flash="off"
          animateShutter={false}
        />
      )}

      <Animated.View
        style={[s.face, { paddingTop: smileTotal, transform: [{ translateY: breathY }, { translateX: glanceX }] }]}
      >
        <View style={s.row}>
          <Eye
            eyelid={clampedLidL}
            pupilX={lPX} pupilY={lPY}
            specularOpacity={specular}
            scanY={scanY}
            botLidAnim={botLidAnim}
            scaleY={eyeScaleY}
            overlayColor={overlayColor}
            overlayOpac={overlayOpac}
          />
          <View style={{ width: EYE_GAP }} />
          <Eye
            eyelid={clampedLidR}
            pupilX={rPX} pupilY={rPY}
            specularOpacity={specular}
            scanY={scanY}
            botLidAnim={botLidAnim}
            scaleY={eyeScaleY}
            overlayColor={overlayColor}
            overlayOpac={overlayOpac}
          />
        </View>

        {/* Sorriso */}
        <Animated.View
          style={[s.smileClip, {
            width: smileW, height: smileClipH, marginTop: EYE_W * 0.20,
            transform: [{ scaleY: mouthFlipAnim }, { scaleY: talkScaleY }, { translateY: talkTranslateY }],
          }]}
        >
          <View style={[s.smileArc, { width: smileW, height: smileArcH, borderRadius: smileArcH * 0.5, ...iosShadow(10, 0.85) }]} />
        </Animated.View>

        {/* Legenda TTS */}
        <Animated.Text style={[s.subtitle, { opacity: subtitleOpac }]}>
          {subtitle}
        </Animated.Text>
      </Animated.View>

      {/* Cabeçalho */}
      <View style={s.headerWrap}>
        <Text style={s.headerText}>© 2026 – ETEO – TECH CARE SENIOR @ {settings.headerTag}</Text>
      </View>

      {/* Debug panel */}
      {settings.showDebug && settings.emotionEnabled && (
        <View style={s.debugWrap}>
          <Text style={[s.debugEmotion, { color: EMOTION_COLORS[debugEmotion] ?? EMOTION_COLORS.neutral }]}>
            {!isReady
              ? 'A carregar modelo…'
              : isCalibrating
              ? 'A calibrar — mantém rosto neutro'
              : `Emoção: ${EMOTION_LABELS[debugEmotion] ?? debugEmotion}`}
          </Text>
          <Text style={s.debugPipeline}>{debugInfo}</Text>
          <Text style={s.debugDetail}>
            cam:{hasCamPerm?'✓':'✗'} · servidor:{settings.serverUrl?'✓':'✗'} · calib:{isCalibrating?'…':'✓'}
          </Text>
        </View>
      )}

      {/* Estado de loading / calibração */}
      {statusText && (
        <View style={s.statusWrap}>
          <Text style={s.statusText}>{statusText}</Text>
        </View>
      )}

      <SettingsPanel
        visible={settingsVisible}
        settings={settings}
        onClose={() => setSettingsVisible(false)}
        onChange={updateSettings}
      />
    </View>
    </TouchableWithoutFeedback>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  bgHalo: {
    position: 'absolute',
    width: SW * 0.75, height: SH * 0.75,
    borderRadius: SW * 0.375,
    backgroundColor: C.glow2,
  },
  hiddenCamera: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
    bottom: 0,
    right: 0,
  },
  face:  { alignItems: 'center' },
  row:   { flexDirection: 'row', alignItems: 'center' },

  // ── Eye ───────────────────────────────────────────────────────────────────────
  eyeOuter: {
    width: EYE_W + 100, height: EYE_H + 100,
    alignItems: 'center', justifyContent: 'center',
  },
  halo: { position: 'absolute', backgroundColor: C.glow2 },
  haloOuter: {
    width: EYE_W + 90, height: EYE_H + 90,
    borderRadius: EYE_R + 45,
  },
  haloInner: {
    width: EYE_W + 44, height: EYE_H + 44,
    borderRadius: EYE_R + 22, backgroundColor: C.glow1,
  },
  eyeBody: {
    width: EYE_W, height: EYE_H,
    borderRadius: EYE_R, backgroundColor: C.cyan,
  },
  eyeClip: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    borderRadius: EYE_R, overflow: 'hidden', backgroundColor: 'transparent',
  },
  moodOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  rimBottom: {
    position: 'absolute', bottom: '-6%', left: '-5%', right: '-5%',
    height: '38%', borderRadius: 999, backgroundColor: 'rgba(0,80,110,0.45)',
  },
  specular: {
    position: 'absolute', top: '9%', left: '9%', width: '42%', height: '32%',
    borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.32)',
  },
  pupilAnchor: {
    position: 'absolute',
    top: (EYE_H - PUPIL) / 2, left: (EYE_W - PUPIL) / 2,
    width: PUPIL, height: PUPIL,
  },
  pupil: {
    width: PUPIL, height: PUPIL,
    borderRadius: PUPIL / 2, backgroundColor: C.pupil,
  },
  pupilGlint: {
    position: 'absolute', top: '14%', left: '18%', width: '26%', height: '20%',
    borderRadius: 999, backgroundColor: 'rgba(0,238,255,0.45)',
  },
  scanLine: {
    position: 'absolute', top: 0, left: '-5%', right: '-5%',
    height: 2, backgroundColor: 'rgba(255,255,255,0.10)',
  },
  eyelid:       { position: 'absolute', top: 0, left: 0, right: 0, height: EYE_H, backgroundColor: C.bg },
  eyelidBottom: { position: 'absolute', bottom: 0, left: 0, right: 0, height: EYE_H, backgroundColor: C.bg },

  // ── Smile ─────────────────────────────────────────────────────────────────────
  smileClip: { overflow: 'hidden', alignItems: 'center' },
  smileArc: {
    position: 'absolute', bottom: 0,
    borderWidth: 2.5, borderColor: C.cyan, backgroundColor: 'transparent',
  },

  // ── Texto ─────────────────────────────────────────────────────────────────────
  subtitle: {
    marginTop: EYE_W * 0.18,
    color: C.cyan,
    fontSize: Math.max(14, EYE_W * 0.13),
    fontStyle: 'italic',
    textAlign: 'center',
    maxWidth: SW * 0.70,
    letterSpacing: 0.5,
    ...Platform.select({
      ios: { shadowColor: C.cyan, shadowOffset: { width:0, height:0 }, shadowOpacity: 0.8, shadowRadius: 6 },
    }),
  },
  headerWrap: {
    position: 'absolute', top: 8, left: 0, right: 0,
    alignItems: 'center',
  },
  headerText: {
    color: 'rgba(0,238,255,0.40)',
    fontSize: 11,
    letterSpacing: 1.2,
    textAlign: 'center',
  },
  debugWrap: {
    position: 'absolute', bottom: 10, right: 12,
    alignItems: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.12)',
    paddingHorizontal: 10,
    paddingVertical: 7,
    maxWidth: SW * 0.55,
  },
  debugEmotion: {
    fontSize: 15, fontWeight: '700', letterSpacing: 1.1, textAlign: 'right',
  },
  debugPipeline: {
    color: 'rgba(0,238,255,0.70)', fontSize: 11, letterSpacing: 0.4,
    textAlign: 'right', marginTop: 3, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  debugDetail: {
    color: 'rgba(0,238,255,0.38)', fontSize: 10, letterSpacing: 0.4,
    textAlign: 'right', marginTop: 2,
  },
  statusWrap: {
    position: 'absolute', bottom: 20,
    paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: 8, borderWidth: 1, borderColor: 'rgba(0,238,255,0.3)',
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  statusText: {
    color: 'rgba(0,238,255,0.7)', fontSize: 13, letterSpacing: 0.5,
  },
});
