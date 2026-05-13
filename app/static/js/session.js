const LANG_NAMES = { en: 'English', no: 'Norsk', ru: 'Русский' };

function initSession(code, initialLang) {
  const feed    = document.getElementById('feed');
  const ended   = document.getElementById('ended');
  const langLabel = document.getElementById('lang-label');
  const switcher  = document.getElementById('lang-switcher');

  let lang = initialLang;
  const entries = []; // oldest-first: { translations, original }
  let interimEl = null;
  let interimData = null;

  Object.entries(LANG_NAMES).forEach(([c, name]) => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = name;
    if (c === lang) opt.selected = true;
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
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_lang', lang }));
    }
  });

  // Rebuild feed: prepend oldest-first so newest ends up at the top
  function rerenderAll() {
    feed.innerHTML = '';
    entries.forEach(entry => {
      feed.prepend(createEntry(entry.translations, entry.original, false, false));
    });
    if (interimData) {
      interimEl = createEntry(interimData.translations, interimData.original, true, false);
      feed.prepend(interimEl);
    }
  }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${code}/client?lang=${lang}`);

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'session_end') {
      ended.classList.remove('hidden');
      ws.close();
      return;
    }

    if (msg.type !== 'transcript') return;

    if (!msg.is_final) {
      interimData = { translations: msg.translations, original: msg.original };
      if (!interimEl) {
        interimEl = createEntry(msg.translations, msg.original, true, true);
        feed.prepend(interimEl);
      } else {
        interimEl.querySelector('.transcript-translated').textContent = msg.translations?.[lang] || msg.original;
        interimEl.querySelector('.transcript-original').textContent = msg.original;
      }
    } else {
      entries.push({ translations: msg.translations, original: msg.original });
      if (interimEl) {
        interimEl = null;
        interimData = null;
        rerenderAll();
      } else {
        feed.prepend(createEntry(msg.translations, msg.original, false, true));
      }
    }
  };

  ws.onclose = () => {
    if (!ended.classList.contains('hidden')) return;
    ended.textContent = 'Disconnected. Please refresh to reconnect.';
    ended.classList.remove('hidden');
  };

  function createEntry(translations, original, isInterim, animate) {
    const translated = translations?.[lang] || original;
    const div = document.createElement('div');
    div.className = 'transcript-entry' + (isInterim ? ' interim' : '');
    if (animate && !isInterim) {
      div.classList.add('entry-new');
      div.addEventListener('animationend', () => div.classList.remove('entry-new'), { once: true });
    }
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
