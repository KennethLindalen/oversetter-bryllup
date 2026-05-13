const LANG_NAMES = { en: 'English', no: 'Norsk', ru: 'Русский' };

function initSession(code, initialLang) {
  const feed = document.getElementById('feed');
  const ended = document.getElementById('ended');
  const langLabel = document.getElementById('lang-label');
  const switcher = document.getElementById('lang-switcher');

  let lang = initialLang;
  const entries = []; // { translations, original, isInterim }

  // Populate language switcher
  Object.entries(LANG_NAMES).forEach(([code, name]) => {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = name;
    if (code === lang) opt.selected = true;
    switcher.appendChild(opt);
  });

  function updateLangLabel() {
    langLabel.textContent = LANG_NAMES[lang] || lang;
  }
  updateLangLabel();

  switcher.addEventListener('change', () => {
    lang = switcher.value;
    updateLangLabel();
    rerenderAll();
  });

  function rerenderAll() {
    feed.innerHTML = '';
    entries.forEach((entry) => {
      const el = createEntry(entry.translations, entry.original, entry.isInterim);
      feed.appendChild(el);
    });
    feed.scrollTop = feed.scrollHeight;
  }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${code}/client`);

  let interimIndex = null;

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'session_end') {
      ended.classList.remove('hidden');
      ws.close();
      return;
    }

    if (msg.type !== 'transcript') return;

    if (!msg.is_final) {
      if (interimIndex === null) {
        entries.push({ translations: msg.translations, original: msg.original, isInterim: true });
        interimIndex = entries.length - 1;
        feed.appendChild(createEntry(msg.translations, msg.original, true));
      } else {
        entries[interimIndex] = { translations: msg.translations, original: msg.original, isInterim: true };
        const els = feed.querySelectorAll('.transcript-entry');
        const el = els[interimIndex];
        if (el) {
          el.querySelector('.transcript-translated').textContent = msg.translations?.[lang] || msg.original;
          el.querySelector('.transcript-original').textContent = msg.original;
        }
      }
    } else {
      if (interimIndex !== null) {
        entries[interimIndex] = { translations: msg.translations, original: msg.original, isInterim: false };
        interimIndex = null;
        rerenderAll();
      } else {
        entries.push({ translations: msg.translations, original: msg.original, isInterim: false });
        feed.appendChild(createEntry(msg.translations, msg.original, false));
      }
    }

    feed.scrollTop = feed.scrollHeight;
  };

  ws.onclose = () => {
    if (!ended.classList.contains('hidden')) return;
    ended.textContent = 'Disconnected. Please refresh to reconnect.';
    ended.classList.remove('hidden');
  };

  function createEntry(translations, original, isInterim) {
    const translated = translations?.[lang] || original;
    const div = document.createElement('div');
    div.className = 'transcript-entry' + (isInterim ? ' interim' : '');
    div.innerHTML = `
      <div class="transcript-translated">${escHtml(translated)}</div>
      <div class="transcript-original">${escHtml(original)}</div>
    `;
    return div;
  }

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
