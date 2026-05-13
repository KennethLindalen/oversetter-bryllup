let keyphrase = '';
let sessionCode = '';
let ws = null;
let recognition = null;
let isRecording = false;

// ── Auth ─────────────────────────────────────────────────────────────────────

document.getElementById('auth-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  keyphrase = document.getElementById('keyphrase').value;
  const res = await fetch('/api/auth/admin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyphrase }),
  });
  if (res.ok) {
    document.getElementById('auth-panel').classList.add('hidden');
    document.getElementById('admin-panel').classList.remove('hidden');
  } else {
    document.getElementById('auth-error').classList.remove('hidden');
  }
});

// ── Session start/end ────────────────────────────────────────────────────────

document.getElementById('start-btn').addEventListener('click', async () => {
  const res = await fetch('/api/session/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyphrase }),
  });
  if (!res.ok) return;
  const data = await res.json();
  sessionCode = data.code;

  document.getElementById('session-code').textContent = sessionCode;
  document.getElementById('pre-session').classList.add('hidden');
  document.getElementById('active-session').classList.remove('hidden');

  connectWs();
});

document.getElementById('end-btn').addEventListener('click', async () => {
  stopRecording();
  await fetch('/api/session/end', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyphrase, code: sessionCode }),
  });
  if (ws) ws.close();
  document.getElementById('active-session').classList.add('hidden');
  document.getElementById('pre-session').classList.remove('hidden');
  document.getElementById('preview').textContent = 'Transcript will appear here…';
  document.getElementById('user-count').textContent = '0 viewers connected';
  sessionCode = '';
});

// ── WebSocket ────────────────────────────────────────────────────────────────

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${sessionCode}/admin`);

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'user_count') {
      const n = msg.count;
      document.getElementById('user-count').textContent = `${n} viewer${n !== 1 ? 's' : ''} connected`;
    }
  };
}

// Maps select value → { source: LT code or "auto", recognitionLang: BCP-47 }
const LANG_MAP = {
  'auto':  { source: 'auto', recognitionLang: 'nb-NO' },
  'en-US': { source: 'en',   recognitionLang: 'en-US' },
  'nb-NO': { source: 'nb',   recognitionLang: 'nb-NO' },
  'ru-RU': { source: 'ru',   recognitionLang: 'ru-RU' },
};

function getLangConfig() {
  return LANG_MAP[document.getElementById('speech-lang').value] || LANG_MAP['auto'];
}

function sendTranscript(text, isFinal) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const { source } = getLangConfig();
  ws.send(JSON.stringify({ type: 'transcript', text, is_final: isFinal, source }));
}

// ── Speech Recognition ───────────────────────────────────────────────────────

const micBtn = document.getElementById('mic-btn');
const micHint = document.getElementById('mic-hint');
const preview = document.getElementById('preview');
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (!SpeechRecognition) {
  micBtn.disabled = true;
  micHint.textContent = 'Speech recognition requires Chrome or Edge.';
}

micBtn.addEventListener('click', () => {
  if (!sessionCode) return;
  isRecording ? stopRecording() : startRecording();
});

function startRecording() {
  recognition = new SpeechRecognition();
  recognition.lang = getLangConfig().recognitionLang;
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (event) => {
    let interim = '';
    let final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final += text;
      } else {
        interim += text;
      }
    }
    if (interim) {
      preview.textContent = interim;
      sendTranscript(interim, false);
    }
    if (final) {
      preview.textContent = final;
      sendTranscript(final, true);
    }
  };

  recognition.onend = () => {
    if (isRecording) recognition.start();
  };

  recognition.onerror = (e) => {
    if (e.error === 'not-allowed') {
      micHint.textContent = 'Microphone access denied.';
      stopRecording();
    }
  };

  recognition.start();
  isRecording = true;
  micBtn.classList.add('recording');
  micHint.textContent = 'Recording — click to stop';
}

function stopRecording() {
  if (recognition) {
    recognition.onend = null;
    recognition.stop();
    recognition = null;
  }
  isRecording = false;
  micBtn.classList.remove('recording');
  micHint.textContent = 'Click to start microphone';
}
