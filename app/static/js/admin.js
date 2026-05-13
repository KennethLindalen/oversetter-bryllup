let keyphrase = '';
let sessionCode = '';
let ws = null;
let mediaRecorder = null;
let isRecording = false;

const CHUNK_MS = 10000;

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

// ── Recording ────────────────────────────────────────────────────────────────

const micBtn = document.getElementById('mic-btn');
const micHint = document.getElementById('mic-hint');
const preview = document.getElementById('preview');

micBtn.addEventListener('click', () => {
  if (!sessionCode) return;
  isRecording ? stopRecording() : startRecording();
});

async function startRecording() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    micHint.textContent = 'Microphone access denied.';
    return;
  }

  mediaRecorder = new MediaRecorder(stream);

  mediaRecorder.ondataavailable = async (e) => {
    if (e.data.size < 1500) return;
    const lang = document.getElementById('speech-lang').value;

    micHint.textContent = 'Processing…';

    const form = new FormData();
    form.append('audio', e.data, 'chunk.webm');
    form.append('code', sessionCode);
    form.append('keyphrase', keyphrase);
    form.append('lang', lang);

    try {
      const res = await fetch('/api/transcribe', { method: 'POST', body: form });
      if (res.status === 429) {
        micHint.textContent = 'Rate limited — speak slower or use longer pauses';
      } else if (res.ok) {
        const data = await res.json();
        if (data.text) preview.textContent = data.text;
      }
    } catch (err) {
      console.error('Transcription error:', err);
    }

    if (isRecording) micHint.textContent = 'Recording — click to stop';
  };

  mediaRecorder.start(CHUNK_MS);
  isRecording = true;
  micBtn.classList.add('recording');
  micHint.textContent = 'Recording — click to stop';
}

function stopRecording() {
  if (mediaRecorder) {
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    mediaRecorder.stop();
    mediaRecorder = null;
  }
  isRecording = false;
  micBtn.classList.remove('recording');
  micHint.textContent = 'Click to start microphone';
}
