function initSession(code, lang) {
  const feed = document.getElementById('feed');
  const ended = document.getElementById('ended');
  const langLabel = document.getElementById('lang-label');

  const LANG_NAMES = { en: 'English', no: 'Norsk', ru: 'Русский' };
  langLabel.textContent = LANG_NAMES[lang] || lang;

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${code}/client`);

  let interimEntry = null;

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'session_end') {
      ended.classList.remove('hidden');
      ws.close();
      return;
    }

    if (msg.type !== 'transcript') return;

    const translated = msg.translations?.[lang] || msg.original;
    const original = msg.original;

    if (!msg.is_final) {
      if (!interimEntry) {
        interimEntry = createEntry(translated, original, true);
        feed.appendChild(interimEntry);
      } else {
        interimEntry.querySelector('.transcript-translated').textContent = translated;
        interimEntry.querySelector('.transcript-original').textContent = original;
      }
    } else {
      if (interimEntry) {
        interimEntry.remove();
        interimEntry = null;
      }
      const entry = createEntry(translated, original, false);
      feed.appendChild(entry);
    }

    feed.scrollTop = feed.scrollHeight;
  };

  ws.onclose = () => {
    if (!ended.classList.contains('hidden')) return;
    ended.textContent = 'Disconnected. Please refresh to reconnect.';
    ended.classList.remove('hidden');
  };

  function createEntry(translated, original, isInterim) {
    const div = document.createElement('div');
    div.className = 'transcript-entry' + (isInterim ? ' interim' : '');
    div.innerHTML = `
      <div class="transcript-translated">${escHtml(translated)}</div>
      <div class="transcript-original">${escHtml(original)}</div>
    `;
    return div;
  }

  function escHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
