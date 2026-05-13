let keyphrase = '';
let sessionCode = '';
let ws = null;
let mediaRecorder = null;
let isRecording = false;
let recordingStream = null;

const CHUNK_MS = 3000;

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
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    micHint.textContent = 'Microphone access denied.';
    return;
  }
  isRecording = true;
  micBtn.classList.add('recording');
  micHint.textContent = 'Recording — click to stop';
  recordCycle();
}

function recordCycle() {
  if (!isRecording || !recordingStream) return;

  const chunks = [];
  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';

  const recorder = new MediaRecorder(recordingStream, { mimeType });
  mediaRecorder = recorder;

  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  recorder.onstop = async () => {
    if (!isRecording) return;

    // Start next cycle immediately so there's no gap while this chunk is uploading
    recordCycle();

    const blob = new Blob(chunks, { type: mimeType });
    if (blob.size < 1500) return;

    const lang = document.getElementById('speech-lang').value;
    const form = new FormData();
    form.append('audio', blob, 'chunk.webm');
    form.append('code', sessionCode);
    form.append('keyphrase', keyphrase);
    form.append('lang', lang);

    try {
      const res = await fetch('/api/transcribe', { method: 'POST', body: form });
      if (res.status === 429) {
        micHint.textContent = 'Rate limited — speak slower or use longer pauses';
      } else if (res.status === 404) {
        stopRecording();
        micHint.textContent = 'Session lost — please end and restart the session';
      } else if (res.ok) {
        const data = await res.json();
        if (data.text) preview.textContent = data.text;
      }
    } catch (err) {
      console.error('Transcription error:', err);
    }
  };

  recorder.start();
  setTimeout(() => {
    if (recorder.state === 'recording') recorder.stop();
  }, CHUNK_MS);
}

function stopRecording() {
  isRecording = false;
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }
  if (recordingStream) {
    recordingStream.getTracks().forEach(t => t.stop());
    recordingStream = null;
  }
  mediaRecorder = null;
  micBtn.classList.remove('recording');
  micHint.textContent = 'Click to start microphone';
}
