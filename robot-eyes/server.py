#!/usr/bin/env python3
"""
server.py — Robot Eyes emotion metric server.
Aceita um JPEG via POST /emotion, corre MediaPipe FaceMesh,
devolve métricas brutas: ear, mar, smile, brow.
A classificação fica no React Native hook.

Endpoints:
    POST /emotion   — analisa frame, devolve métricas
    POST /log       — regista emoção confirmada (chamado pela app RN)
    GET  /log       — devolve histórico JSON (?limit=N)
    GET  /          — dashboard HTML com gráficos

Uso:
    pip install flask flask-cors
    python server.py
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import mediapipe as mp
import numpy as np
import cv2
import json
import os
import time

app = Flask(__name__)
CORS(app)

# ── Dashboard HTML ─────────────────────────────────────────────────────────────
_DASHBOARD = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robot Eyes — Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%;
    overflow: hidden;
    background: #080C0E;
    color: #D0F4F8;
    font-family: 'Courier New', monospace;
  }
  body {
    display: flex;
    flex-direction: column;
    padding: 16px;
    gap: 10px;
  }
  h1  { color: #00EEFF; font-size: 13px; letter-spacing: 3px; text-transform: uppercase; flex-shrink: 0; }
  h2  { color: rgba(0,238,255,0.50); font-size: 10px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; flex-shrink: 0; }
  .grid {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 2fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 10px;
  }
  .card {
    background: #0D1417;
    border: 1px solid rgba(0,238,255,0.15);
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .wide { grid-column: 1 / -1; }
  .chart-wrap { flex: 1; min-height: 0; position: relative; }
  table  { width: 100%; border-collapse: collapse; font-size: 12px; }
  th     { color: rgba(0,238,255,0.50); text-align: left; padding: 4px 8px; border-bottom: 1px solid rgba(0,238,255,0.15); font-weight: normal; letter-spacing: 1px; }
  td     { padding: 4px 8px; border-bottom: 1px solid rgba(0,238,255,0.06); }
  .log-wrap { flex: 1; overflow-y: auto; min-height: 0; }
  #status { font-size: 11px; color: rgba(0,238,255,0.30); flex-shrink: 0; }
  .controls { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
  .controls button {
    background: transparent; border: 1px solid rgba(0,238,255,0.20);
    color: rgba(0,238,255,0.55); font-family: inherit; font-size: 11px;
    padding: 4px 10px; border-radius: 5px; cursor: pointer; letter-spacing: 0.5px;
  }
  .controls button:hover  { border-color: rgba(0,238,255,0.50); color: #00EEFF; }
  .controls button.active { background: rgba(0,238,255,0.12); border-color: #00EEFF; color: #00EEFF; }
  .controls .sep { flex: 1; }
  .controls .live { background: rgba(0,238,255,0.08); border-color: rgba(0,238,255,0.35); color: #00EEFF; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>&#169; Robot Eyes &mdash; Emotion Dashboard</h1>
<div class="grid">
  <div class="card">
    <h2>Timeline</h2>
    <div class="controls" style="margin-bottom:8px">
      <button onclick="setWin(15)"  id="w15">15min</button>
      <button onclick="setWin(30)"  id="w30" class="active">30min</button>
      <button onclick="setWin(60)"  id="w60">1h</button>
      <button onclick="setWin(180)" id="w180">3h</button>
      <button onclick="setWin(0)"   id="wall">Tudo</button>
      <span class="sep"></span>
      <button onclick="pan(-1)">&#9664;</button>
      <button onclick="pan(1)"  id="btn-fwd">&#9654;</button>
      <button onclick="goLive()" id="btn-live" class="live">Ao vivo</button>
    </div>
    <div class="chart-wrap"><canvas id="c-timeline"></canvas></div>
  </div>
  <div class="card">
    <h2>Distribuição</h2>
    <div class="chart-wrap"><canvas id="c-dist"></canvas></div>
  </div>
  <div class="card">
    <h2>Log recente</h2>
    <div class="log-wrap">
      <table><thead><tr><th>Hora</th><th>Emoção</th></tr></thead>
      <tbody id="t-body"></tbody></table>
    </div>
  </div>
  <div class="card">
    <h2>Enviar mensagem ao robot</h2>
    <div style="display:flex;flex-direction:column;gap:8px;flex:1;min-height:0">
      <textarea id="msg-input"
        placeholder="Escreve uma mensagem... (Ctrl+Enter para enviar)"
        style="flex:1;min-height:0;background:rgba(0,238,255,0.04);border:1px solid rgba(0,238,255,0.15);
               border-radius:8px;color:#D0F4F8;font-family:inherit;font-size:13px;
               padding:10px;resize:none;outline:none;"></textarea>
      <button id="msg-btn" onclick="sendMsg()"
        style="background:rgba(0,238,255,0.10);border:1px solid rgba(0,238,255,0.40);
               color:#00EEFF;font-family:inherit;font-size:12px;letter-spacing:1px;
               padding:8px;border-radius:7px;cursor:pointer;">
        Enviar ao Robot
      </button>
      <p id="msg-status" style="font-size:11px;color:rgba(0,238,255,0.40);min-height:14px;"></p>
    </div>
  </div>
</div>
<p id="status">a carregar...</p>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<script>
let windowMs = 30 * 60 * 1000;  // janela visível (0 = tudo)
let offsetMs  = 0;               // desvio do presente (0 = ao vivo)

function setWin(min) {
  windowMs = min * 60 * 1000;
  if (windowMs === 0) offsetMs = 0;
  ['w15','w30','w60','w180','wall'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', id === 'w' + (min || 'all'));
  });
  updateNavBtns();
  refresh();
}

function pan(dir) {
  if (!windowMs) return;
  offsetMs += dir * windowMs * 0.5;
  if (offsetMs < 0) offsetMs = 0;
  updateNavBtns();
  refresh();
}

function goLive() {
  offsetMs = 0;
  updateNavBtns();
  refresh();
}

function updateNavBtns() {
  const fwd  = document.getElementById('btn-fwd');
  const live = document.getElementById('btn-live');
  if (fwd)  fwd.disabled  = offsetMs === 0;
  if (live) live.classList.toggle('active', offsetMs === 0);
}

const EMOTION_Y = { neutral:0, happy:2, surprised:1, sad:-1, angry:-2 };
const COLORS = { neutral:'#00EEFF', happy:'#88FFAA', surprised:'#FFFFFF', sad:'#5088FF', angry:'#FF5032' };
const LABELS = { neutral:'Neutro', happy:'Alegre', surprised:'Surpreendido', sad:'Triste', angry:'Zangado' };
const GRID_COLOR = 'rgba(0,238,255,0.07)';
const TICK_COLOR = 'rgba(0,238,255,0.45)';

Chart.defaults.color = TICK_COLOR;
Chart.defaults.borderColor = GRID_COLOR;

const timeline = new Chart(document.getElementById('c-timeline'), {
  type: 'line',
  data: { datasets: [{ data: [], borderColor: '#00EEFF', backgroundColor: 'rgba(0,238,255,0.08)',
    stepped: true, tension: 0, pointRadius: 4, pointBackgroundColor: [], borderWidth: 1.5 }] },
  options: {
    animation: false, responsive: true, maintainAspectRatio: false,
    scales: {
      x: { type:'time', time:{ unit:'minute', displayFormats:{ minute:'HH:mm' } },
           ticks:{ color:TICK_COLOR, maxTicksLimit:8 }, grid:{ color:GRID_COLOR } },
      y: { min:-3, max:3, ticks:{ color:TICK_COLOR,
             callback: v => { const k = Object.entries(EMOTION_Y).find(([,val]) => val===v)?.[0]; return k ? LABELS[k] : ''; } },
           grid:{ color:GRID_COLOR } }
    },
    plugins: { legend:{ display:false } }
  }
});

const dist = new Chart(document.getElementById('c-dist'), {
  type: 'doughnut',
  data: {
    labels: Object.values(LABELS),
    datasets: [{ data:[0,0,0,0,0], backgroundColor: Object.values(COLORS),
                 borderWidth:0, hoverOffset:6 }]
  },
  options: {
    animation: false, responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position:'bottom', labels:{ color:'#D0F4F8', font:{ size:11 }, padding:8 } } }
  }
});

function refresh() {
  fetch('/log?limit=300')
    .then(r => r.json())
    .then(log => {
      // Timeline
      const now = Date.now();
      if (windowMs) {
        const end = now - offsetMs;
        timeline.options.scales.x.min = end - windowMs;
        timeline.options.scales.x.max = end;
      } else {
        delete timeline.options.scales.x.min;
        delete timeline.options.scales.x.max;
      }
      // auto-avança apenas em modo ao vivo
      if (offsetMs === 0 && windowMs) timeline.options.scales.x.max = now;
      timeline.data.datasets[0].data = log.map(e => ({ x: new Date(e.timestamp), y: EMOTION_Y[e.emotion] ?? 0 }));
      timeline.data.datasets[0].pointBackgroundColor = log.map(e => COLORS[e.emotion] ?? '#00EEFF');
      timeline.update('none');

      // Distribution
      const counts = { neutral:0, happy:0, surprised:0, sad:0, angry:0 };
      log.forEach(e => { if (e.emotion in counts) counts[e.emotion]++; });
      dist.data.datasets[0].data = Object.values(counts);
      dist.update('none');

      // Table
      document.getElementById('t-body').innerHTML = log.slice(-60).reverse().map(e => {
        const t = new Date(e.timestamp).toLocaleTimeString('pt-PT');
        return '<tr><td>' + t + '</td><td style="color:' + (COLORS[e.emotion]||'#D0F4F8') + '">'
             + (LABELS[e.emotion] || e.emotion) + '</td></tr>';
      }).join('');

      document.getElementById('status').textContent =
        log.length + ' registos · atualizado ' + new Date().toLocaleTimeString('pt-PT');
    })
    .catch(() => { document.getElementById('status').textContent = 'erro ao carregar dados'; });
}

refresh();
setInterval(refresh, 5000);

function sendMsg() {
  const input  = document.getElementById('msg-input');
  const status = document.getElementById('msg-status');
  const text   = input.value.trim();
  if (!text) return;
  document.getElementById('msg-btn').disabled = true;
  fetch('/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  .then(r => r.json())
  .then(() => {
    status.textContent = 'Enviado ✓';
    input.value = '';
    setTimeout(() => { status.textContent = ''; }, 3000);
  })
  .catch(() => { status.textContent = 'Erro ao enviar'; })
  .finally(() => { document.getElementById('msg-btn').disabled = false; });
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('msg-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendMsg(); }
  });
});
</script>
</body>
</html>"""

# ── Emotion log ────────────────────────────────────────────────────────────────
_pending_message = None

_LOG_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'emotion_log.json')
_MAX_ENTRIES = 2000
_emotion_log = []

def _load_log():
    global _emotion_log
    if os.path.exists(_LOG_FILE):
        try:
            with open(_LOG_FILE) as f:
                _emotion_log = json.load(f)
        except Exception:
            _emotion_log = []

def _save_log():
    try:
        with open(_LOG_FILE, 'w') as f:
            json.dump(_emotion_log[-_MAX_ENTRIES:], f)
    except Exception:
        pass

_load_log()

# ── Índices de landmarks (iguais a robot_eyes.py) ─────────────────────────────
_L_EYE_TOP, _L_EYE_BOT = 159, 145
_R_EYE_TOP, _R_EYE_BOT = 386, 374
_L_EYE_L,   _L_EYE_R   =  33, 133
_R_EYE_L,   _R_EYE_R   = 263, 362
_L_BROW,    _R_BROW     =  70, 300
_MOUTH_L,   _MOUTH_R    =  61, 291
_MOUTH_TOP, _MOUTH_BOT  =  13,  14
_FACE_TOP,  _FACE_BOT   =  10, 152

# Singleton — inicializado uma vez na startup, não por pedido
face_mesh = mp.solutions.face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=False,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)


def extract_metrics(lms, w: int, h: int):
    """Extrai ear, mar, smile, brow dos landmarks. Devolve None em caso de erro."""
    def y(i): return lms[i].y * h
    def x(i): return lms[i].x * w
    try:
        ear_l = abs(y(_L_EYE_TOP) - y(_L_EYE_BOT)) / (abs(x(_L_EYE_L) - x(_L_EYE_R)) + 1e-6)
        ear_r = abs(y(_R_EYE_TOP) - y(_R_EYE_BOT)) / (abs(x(_R_EYE_L) - x(_R_EYE_R)) + 1e-6)
        ear   = (ear_l + ear_r) / 2

        mar = abs(y(_MOUTH_TOP) - y(_MOUTH_BOT)) / (abs(x(_MOUTH_L) - x(_MOUTH_R)) + 1e-6)

        fh    = abs(y(_FACE_BOT) - y(_FACE_TOP)) + 1e-6
        smile = ((y(_MOUTH_TOP) + y(_MOUTH_BOT)) / 2 - (y(_MOUTH_L) + y(_MOUTH_R)) / 2) / fh

        brow = ((y(_L_EYE_TOP) - y(_L_BROW)) + (y(_R_EYE_TOP) - y(_R_BROW))) / 2 / fh

        return dict(
            ear=round(float(ear),   4),
            mar=round(float(mar),   4),
            smile=round(float(smile), 4),
            brow=round(float(brow),  4),
        )
    except Exception:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template_string(_DASHBOARD)


@app.route('/log', methods=['POST'])
def log_add():
    data    = request.get_json(silent=True) or {}
    emotion = data.get('emotion', 'neutral')
    _emotion_log.append({
        'emotion':   emotion,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    })
    if len(_emotion_log) > _MAX_ENTRIES:
        del _emotion_log[:-_MAX_ENTRIES]
    _save_log()
    return jsonify({'ok': True})


@app.route('/log', methods=['GET'])
def log_get():
    limit = min(int(request.args.get('limit', 200)), _MAX_ENTRIES)
    return jsonify(_emotion_log[-limit:])


@app.route('/message', methods=['POST'])
def message_post():
    global _pending_message
    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if text:
        _pending_message = text
    return jsonify({'ok': True})


@app.route('/message', methods=['GET'])
def message_get():
    global _pending_message
    msg = _pending_message
    _pending_message = None  # consumir — cada mensagem entregue uma vez
    return jsonify({'message': msg})


@app.route('/emotion', methods=['POST'])
def emotion():
    try:
        img_file = request.files.get('image')
        if img_file is None:
            return jsonify({"face": False, "error": "sem campo 'image'"})

        buf = np.frombuffer(img_file.read(), np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"face": False, "error": "decode falhou"})

        h, w   = img.shape[:2]
        rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = face_mesh.process(rgb)

        if not result.multi_face_landmarks:
            return jsonify({"face": False})

        metrics = extract_metrics(result.multi_face_landmarks[0].landmark, w, h)
        if metrics is None:
            return jsonify({"face": False})

        return jsonify({"face": True, "metrics": metrics})

    except Exception as e:
        # Nunca crasha o tablet — devolve face:false em qualquer erro
        return jsonify({"face": False, "error": str(e)})


if __name__ == '__main__':
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'
    print(f"\nRobot Eyes server a correr:")
    print(f"  → http://{local_ip}:5001/         (dashboard)")
    print(f"  → http://{local_ip}:5001/emotion   (API)\n")
    # threaded=False: MediaPipe não é thread-safe
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=False)
