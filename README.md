# Robbie — Robot Eyes

Olhos robóticos animados que detetam expressões faciais em tempo real e reagem com animações e voz em português.

Projeto académico **ETEO 2TIS — Tech Care Senior**.

---

## Estrutura

```
Robbie/
├── robot-eyes/                  # Backend Python + app desktop
│   ├── robot_eyes.py            # App standalone (webcam + OpenCV)
│   ├── server.py                # Servidor Flask (API + dashboard)
│   └── requirements.txt
└── robot-eyes-react-native/     # App mobile React Native / Expo
    ├── App.js                   # Ecrã principal
    ├── hooks/useFaceEmotion.js  # Calibração e classificação de emoções
    └── components/SettingsPanel.js
```

---

## Como funciona

```
[Tablet/Câmara] ──JPEG──▶ [Flask server] ──métricas──▶ [Hook RN] ──emoção──▶ [Olhos animados + TTS]
```

1. O app mobile captura um frame da câmara frontal a cada 1,5 segundos
2. Envia para o servidor Flask (`POST /emotion`)
3. O servidor usa MediaPipe FaceMesh para extrair métricas faciais (EAR, MAR, smile, brow)
4. O hook `useFaceEmotion` classifica a emoção no cliente
5. Os olhos animam e o robot fala em português

---

## robot-eyes — Backend Python

### App standalone (`robot_eyes.py`)

Corre diretamente no computador com webcam, sem necessidade de app mobile.

```bash
cd robot-eyes
pip install -r requirements.txt
python robot_eyes.py
```

- Deteta 7 emoções: `happy`, `sad`, `angry`, `surprise`, `fear`, `disgust`, `neutral`
- Calibra ao rosto neutro do utilizador nos primeiros ~2 segundos
- Janela OpenCV 920×580 com olhos animados, gaze tracking e blink automático

### Servidor Flask (`server.py`)

```bash
cd robot-eyes
python server.py
```

Corre na porta **5001**. Endpoints:

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Dashboard com gráficos (Chart.js) |
| `POST` | `/emotion` | Recebe JPEG, devolve métricas faciais |
| `POST` | `/log` | Regista emoção |
| `GET` | `/log?limit=N` | Devolve histórico |
| `POST` | `/message` | Envia mensagem ao robot |
| `GET` | `/message` | Lê e consome mensagem pendente |

---

## robot-eyes-react-native — App Mobile

### Pré-requisitos

- Node.js + npm
- Expo CLI (`npm install -g expo-cli`)
- Servidor Flask a correr na mesma rede local

### Instalar e correr

```bash
cd robot-eyes-react-native
npm install
npx expo start
```

### Configuração

Abre as definições com **3 toques** no ecrã:

- **URL do servidor** — endereço Flask na rede local (ex: `http://192.168.1.X:5001`)
- **Voz** — ativa/desativa TTS em português
- **Reconhecimento de emoções** — ativa/desativa câmara
- **Sensibilidade** — Baixa / Normal / Alta
- **Frases** — personalizáveis por emoção

Emoções suportadas: `neutral`, `happy`, `sad`, `angry`, `surprised`

---

## Dependências

**Python:** `opencv-python>=4.8.0`, `mediapipe==0.10.14`, `flask>=3.0.0`, `flask-cors>=4.0.0`

**React Native:** Expo ~54, `expo-camera`, `expo-speech`, `expo-navigation-bar`, `@react-native-async-storage/async-storage`

---

© 2026 ETEO — Tech Care Senior
