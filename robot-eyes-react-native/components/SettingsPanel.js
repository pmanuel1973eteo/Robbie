import React, { useState, useRef } from 'react';
import {
  View, Text, Modal, ScrollView, TouchableOpacity,
  Switch, TextInput, StyleSheet, SafeAreaView, Platform,
  useWindowDimensions,
} from 'react-native';

const C = {
  bg:      '#080C0E',
  panel:   '#0D1417',
  border:  'rgba(0,238,255,0.18)',
  cyan:    '#00EEFF',
  cyanDim: 'rgba(0,238,255,0.55)',
  muted:   'rgba(0,238,255,0.35)',
  text:    '#D0F4F8',
  danger:  'rgba(255,80,60,0.75)',
};

const MOOD_LABELS = {
  greeting:  'Saudação inicial',
  neutral:   'Neutro',
  happy:     'Alegre',
  sad:       'Triste',
  angry:     'Zangado',
  surprised: 'Surpreendido',
};

export default function SettingsPanel({ visible, settings, onClose, onChange }) {
  const [expandedMood, setExpandedMood] = useState(null);
  const [testStatus, setTestStatus]     = useState(null); // null | 'loading' | 'ok' | 'error'
  const [testMsg, setTestMsg]           = useState('');
  const testTimer = useRef(null);
  const { width: winW, height: winH } = useWindowDimensions();

  const testConnection = async () => {
    const url = settings.serverUrl?.trim();
    if (!url) { setTestStatus('error'); setTestMsg('URL vazio'); return; }
    setTestStatus('loading');
    setTestMsg('');
    clearTimeout(testTimer.current);
    try {
      const ctrl = new AbortController();
      const tid  = setTimeout(() => ctrl.abort(), 5000);
      const res  = await fetch(`${url}/log?limit=1`, { signal: ctrl.signal });
      clearTimeout(tid);
      if (res.ok) {
        setTestStatus('ok');
        setTestMsg('Servidor acessível ✓');
      } else {
        setTestStatus('error');
        setTestMsg(`HTTP ${res.status}`);
      }
    } catch (e) {
      setTestStatus('error');
      setTestMsg(e.name === 'AbortError' ? 'Timeout (5s)' : 'Sem acesso');
    }
    testTimer.current = setTimeout(() => { setTestStatus(null); setTestMsg(''); }, 5000);
  };

  const set = (patch) => onChange({ ...settings, ...patch });

  const updatePhrase = (mood, idx, text) => {
    const phrases = { ...settings.phrases, [mood]: [...settings.phrases[mood]] };
    phrases[mood][idx] = text;
    onChange({ ...settings, phrases });
  };

  const addPhrase = (mood) => {
    const phrases = { ...settings.phrases, [mood]: [...settings.phrases[mood], ''] };
    onChange({ ...settings, phrases });
  };

  const removePhrase = (mood, idx) => {
    const phrases = {
      ...settings.phrases,
      [mood]: settings.phrases[mood].filter((_, i) => i !== idx),
    };
    onChange({ ...settings, phrases });
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      statusBarTranslucent
      hardwareAccelerated
      onRequestClose={onClose}
    >
      <View style={[s.overlay, { width: winW, height: winH }]}>
        <SafeAreaView style={s.card}>
          {/* Header */}
          <View style={s.header}>
            <Text style={s.title}>Definições</Text>
            <TouchableOpacity onPress={onClose} style={s.closeBtn} hitSlop={{ top:10,bottom:10,left:10,right:10 }}>
              <Text style={s.closeText}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView
            style={s.body}
            contentContainerStyle={{ paddingBottom: 32 }}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            {/* ── Toggles ── */}
            <Text style={s.sectionLabel}>GERAL</Text>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>Voz</Text>
                <Text style={s.rowSub}>Robot fala ao detetar emoções</Text>
              </View>
              <Switch
                value={settings.voiceEnabled}
                onValueChange={(v) => set({ voiceEnabled: v })}
                trackColor={{ false: '#1A2A2E', true: '#005566' }}
                thumbColor={settings.voiceEnabled ? C.cyan : '#445'}
                ios_backgroundColor="#1A2A2E"
              />
            </View>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>Reconhecimento de emoções</Text>
                <Text style={s.rowSub}>Usa a câmara frontal para detetar o humor</Text>
              </View>
              <Switch
                value={settings.emotionEnabled}
                onValueChange={(v) => set({ emotionEnabled: v })}
                trackColor={{ false: '#1A2A2E', true: '#005566' }}
                thumbColor={settings.emotionEnabled ? C.cyan : '#445'}
                ios_backgroundColor="#1A2A2E"
              />
            </View>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>Mensagens de debug</Text>
                <Text style={s.rowSub}>Mostra estado da câmara e emoção detetada</Text>
              </View>
              <Switch
                value={settings.showDebug}
                onValueChange={(v) => set({ showDebug: v })}
                trackColor={{ false: '#1A2A2E', true: '#005566' }}
                thumbColor={settings.showDebug ? C.cyan : '#445'}
                ios_backgroundColor="#1A2A2E"
              />
            </View>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>Etiqueta do cabeçalho</Text>
                <Text style={s.rowSub}>Texto após "@" no topo do ecrã</Text>
              </View>
              <TextInput
                style={s.tagInput}
                value={settings.headerTag}
                onChangeText={(t) => set({ headerTag: t })}
                placeholder="Eco-Digithon Portugal"
                placeholderTextColor="#334"
                autoCapitalize="none"
                returnKeyType="done"
                maxLength={24}
              />
            </View>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>Sensibilidade de emoção</Text>
                <Text style={s.rowSub}>Facilidade de deteção de expressões faciais</Text>
              </View>
              <View style={s.segmentRow}>
                {[['Baixa', 0.5], ['Normal', 1.0], ['Alta', 1.5]].map(([label, val]) => (
                  <TouchableOpacity
                    key={label}
                    style={[s.segment, settings.sensitivity === val && s.segmentActive]}
                    onPress={() => set({ sensitivity: val })}
                  >
                    <Text style={[s.segmentText, settings.sensitivity === val && s.segmentTextActive]}>
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            {/* ── Servidor ── */}
            <Text style={[s.sectionLabel, { marginTop: 24 }]}>SERVIDOR</Text>

            <View style={s.row}>
              <View style={s.rowLeft}>
                <Text style={s.rowTitle}>URL do servidor</Text>
                <Text style={s.rowSub}>Endereço Flask na rede local</Text>
              </View>
              <TextInput
                style={[s.tagInput, { minWidth: 200, textAlign: 'left', letterSpacing: 0 }]}
                value={settings.serverUrl}
                onChangeText={(t) => { set({ serverUrl: t.trim() }); setTestStatus(null); }}
                placeholder="http://192.168.1.X:5000"
                placeholderTextColor="#334"
                keyboardType="url"
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="done"
              />
            </View>

            <View style={s.testRow}>
              <TouchableOpacity
                style={[s.testBtn, testStatus === 'ok' && s.testBtnOk, testStatus === 'error' && s.testBtnErr]}
                onPress={testConnection}
                disabled={testStatus === 'loading'}
                activeOpacity={0.7}
              >
                <Text style={s.testBtnText}>
                  {testStatus === 'loading' ? 'A testar…' : 'Testar ligação'}
                </Text>
              </TouchableOpacity>
              {testMsg ? (
                <Text style={[s.testMsg, testStatus === 'ok' ? s.testMsgOk : s.testMsgErr]}>
                  {testMsg}
                </Text>
              ) : null}
            </View>

            {/* ── Phrases ── */}
            <Text style={[s.sectionLabel, { marginTop: 24 }]}>FRASES</Text>

            {Object.entries(MOOD_LABELS).map(([mood, label]) => {
              const open = expandedMood === mood;
              return (
                <View key={mood} style={s.moodBlock}>
                  <TouchableOpacity
                    style={s.moodHeader}
                    onPress={() => setExpandedMood(open ? null : mood)}
                    activeOpacity={0.7}
                  >
                    <Text style={s.moodLabel}>{label}</Text>
                    <Text style={s.moodCount}>{settings.phrases[mood]?.length ?? 0} frases</Text>
                    <Text style={s.chevron}>{open ? '▲' : '▼'}</Text>
                  </TouchableOpacity>

                  {open && (
                    <View style={s.phraseList}>
                      {(settings.phrases[mood] ?? []).map((phrase, idx) => (
                        <View key={idx} style={s.phraseRow}>
                          <TextInput
                            style={s.phraseInput}
                            value={phrase}
                            onChangeText={(t) => updatePhrase(mood, idx, t)}
                            placeholder="Escreve uma frase…"
                            placeholderTextColor="#334"
                            multiline
                            returnKeyType="done"
                          />
                          <TouchableOpacity
                            onPress={() => removePhrase(mood, idx)}
                            style={s.removeBtn}
                            hitSlop={{ top:8,bottom:8,left:8,right:8 }}
                          >
                            <Text style={s.removeText}>✕</Text>
                          </TouchableOpacity>
                        </View>
                      ))}
                      <TouchableOpacity onPress={() => addPhrase(mood)} style={s.addBtn}>
                        <Text style={s.addText}>+ Adicionar frase</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              );
            })}
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.75)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    maxWidth: 560,
    maxHeight: '90%',
    backgroundColor: C.panel,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: C.border,
    ...Platform.select({
      ios: { shadowColor: C.cyan, shadowOffset:{width:0,height:0}, shadowOpacity:0.25, shadowRadius:24 },
      android: { elevation: 12 },
    }),
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 18,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
  },
  title: {
    color: C.cyan,
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  closeBtn: {
    width: 32, height: 32,
    alignItems: 'center', justifyContent: 'center',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: C.border,
  },
  closeText: { color: C.cyanDim, fontSize: 14 },

  body: { paddingHorizontal: 24, paddingTop: 16 },

  sectionLabel: {
    color: C.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 2,
    marginBottom: 10,
  },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,238,255,0.07)',
  },
  rowLeft: { flex: 1, marginRight: 16 },
  rowTitle: { color: C.text, fontSize: 15, fontWeight: '500' },
  rowSub:   { color: C.muted, fontSize: 12, marginTop: 2 },

  // Moods
  moodBlock: {
    marginBottom: 4,
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.10)',
    borderRadius: 10,
    overflow: 'hidden',
  },
  moodHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 13,
    backgroundColor: 'rgba(0,238,255,0.04)',
  },
  moodLabel: { flex: 1, color: C.text, fontSize: 14, fontWeight: '500' },
  moodCount: { color: C.muted, fontSize: 12, marginRight: 12 },
  chevron:   { color: C.muted, fontSize: 11 },

  phraseList: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  phraseRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  phraseInput: {
    flex: 1,
    backgroundColor: 'rgba(0,238,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.15)',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: C.text,
    fontSize: 13,
    minHeight: 38,
  },
  removeBtn: {
    width: 30, height: 38,
    alignItems: 'center', justifyContent: 'center',
  },
  removeText: { color: C.danger, fontSize: 14 },
  addBtn: {
    paddingVertical: 8,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.15)',
    borderRadius: 8,
    borderStyle: 'dashed',
    marginTop: 2,
  },
  addText: { color: C.cyanDim, fontSize: 13 },

  tagInput: {
    backgroundColor: 'rgba(0,238,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.15)',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    color: C.cyan,
    fontSize: 13,
    letterSpacing: 1,
    minWidth: 110,
    textAlign: 'right',
  },

  segmentRow: { flexDirection: 'row', gap: 4 },
  segment: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.20)',
    backgroundColor: 'transparent',
  },
  segmentActive: {
    backgroundColor: 'rgba(0,238,255,0.15)',
    borderColor: C.cyan,
  },
  segmentText:       { color: C.muted, fontSize: 12 },
  segmentTextActive: { color: C.cyan,  fontWeight: '600' },

  testRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,238,255,0.07)',
  },
  testBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: 'rgba(0,238,255,0.30)',
    backgroundColor: 'rgba(0,238,255,0.06)',
  },
  testBtnOk:  { borderColor: 'rgba(80,220,120,0.50)', backgroundColor: 'rgba(80,220,120,0.08)' },
  testBtnErr: { borderColor: 'rgba(255,80,60,0.50)',  backgroundColor: 'rgba(255,80,60,0.08)'  },
  testBtnText: { color: C.cyan, fontSize: 13, letterSpacing: 0.5 },
  testMsg:     { fontSize: 13, letterSpacing: 0.3, flex: 1 },
  testMsgOk:   { color: 'rgba(80,220,120,0.90)' },
  testMsgErr:  { color: 'rgba(255,100,80,0.90)' },
});
