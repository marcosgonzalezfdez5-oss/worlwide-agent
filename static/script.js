const messagesArea = document.getElementById('messages');
const form        = document.getElementById('chatForm');
const textarea    = document.getElementById('messageInput');
const sendBtn     = document.getElementById('sendBtn');
const resetBtn    = document.getElementById('resetBtn');

let isLoading = false;

// ── Auto-resize textarea ─────────────────────────────────────
textarea.addEventListener('input', () => {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px';
  sendBtn.disabled = !textarea.value.trim() || isLoading;
});

// ── Helpers ──────────────────────────────────────────────────
function scrollBottom() {
  messagesArea.scrollTo({ top: messagesArea.scrollHeight, behavior: 'smooth' });
}

function setLoading(on) {
  isLoading = on;
  textarea.disabled = on;
  sendBtn.disabled  = on || !textarea.value.trim();
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Basic markdown: **bold**, `code`, newlines
function renderText(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function weatherIcon(type) {
  const t = (type || '').toLowerCase();
  if (t.includes('thunder') || t.includes('storm'))                       return 'fa-bolt';
  if (t.includes('snow')    || t.includes('blizzard'))                    return 'fa-snowflake';
  if (t.includes('rain')    || t.includes('drizzle') || t.includes('shower')) return 'fa-cloud-rain';
  if (t.includes('fog')     || t.includes('mist')    || t.includes('haze'))   return 'fa-smog';
  if (t.includes('overcast'))                                              return 'fa-cloud';
  if (t.includes('cloud')   || t.includes('partly'))                      return 'fa-cloud-sun';
  if (t.includes('wind')    || t.includes('breezy'))                      return 'fa-wind';
  if (t.includes('sun')     || t.includes('clear'))                       return 'fa-sun';
  return 'fa-globe';
}

function fmtTime(str) {
  if (!str || str === 'Unavailable') return '—';
  try {
    const d = new Date(str);
    if (isNaN(d)) return str;
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch { return str; }
}

// ── DOM builders ─────────────────────────────────────────────
function makeAvatar(role) {
  const el = document.createElement('div');
  el.className = `avatar ${role}`;
  el.innerHTML = role === 'agent'
    ? '<i class="fa-solid fa-globe"></i>'
    : '<i class="fa-solid fa-user"></i>';
  return el;
}

function hideWelcome() {
  document.getElementById('welcome')?.remove();
}

function appendUserMsg(text) {
  hideWelcome();
  const row = document.createElement('div');
  row.className = 'message user';
  row.innerHTML = `
    <div class="avatar user"><i class="fa-solid fa-user"></i></div>
    <div class="msg-content">${esc(text)}</div>
  `;
  messagesArea.appendChild(row);
  scrollBottom();
}

function appendTyping() {
  const row = document.createElement('div');
  row.className = 'message agent';
  row.id = 'typing-row';
  row.innerHTML = `
    <div class="avatar agent"><i class="fa-solid fa-globe"></i></div>
    <div class="msg-content">
      <div class="typing">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
    </div>
  `;
  messagesArea.appendChild(row);
  scrollBottom();
}

function removeTyping() {
  document.getElementById('typing-row')?.remove();
}

function appendText(text, isError = false) {
  const row = document.createElement('div');
  row.className = `message ${isError ? 'error' : 'agent'}`;
  row.innerHTML = `
    <div class="avatar agent"><i class="fa-solid fa-globe"></i></div>
    <div class="msg-content">${renderText(text)}</div>
  `;
  messagesArea.appendChild(row);
  scrollBottom();
}

function buildWeatherCard(item, delay) {
  const card = document.createElement('div');
  card.className = 'wcard';
  card.style.animationDelay = `${delay}s`;

  if (item.error) {
    card.innerHTML = `
      <div class="wcard-error">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>${esc(item.location)}: ${esc(item.error)}</span>
      </div>`;
    return card;
  }

  card.innerHTML = `
    <div class="wcard-head">
      <div class="wcard-icon"><i class="fa-solid ${weatherIcon(item.weather_type)}"></i></div>
      <div>
        <div class="wcard-city">${esc(item.location)}</div>
        <div class="wcard-desc">${esc(item.weather_type)}</div>
      </div>
    </div>
    <div class="wcard-temp">
      ${esc(item.temperature_c)}°C
      <small>/ ${esc(item.temperature_f)}°F</small>
    </div>
    <div class="wcard-grid">
      <div class="wcard-item">
        <i class="fa-solid fa-droplet"></i>
        <span>Humidity&nbsp;<strong>${esc(item.humidity_percent)}%</strong></span>
      </div>
      <div class="wcard-item">
        <i class="fa-solid fa-clock"></i>
        <span>Local&nbsp;<strong>${fmtTime(item.current_time)}</strong></span>
      </div>
      <div class="wcard-item span2">
        <i class="fa-solid fa-location-dot"></i>
        <span>Timezone&nbsp;<strong>${esc(item.timezone)}</strong></span>
      </div>
    </div>`;
  return card;
}

function appendWeather(data) {
  const row = document.createElement('div');
  row.className = 'message agent';

  const avatar = document.createElement('div');
  avatar.className = 'avatar agent';
  avatar.innerHTML = '<i class="fa-solid fa-globe"></i>';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const cards = document.createElement('div');
  cards.className = 'weather-cards';
  data.forEach((item, i) => cards.appendChild(buildWeatherCard(item, i * 0.06)));

  content.appendChild(cards);
  row.appendChild(avatar);
  row.appendChild(content);
  messagesArea.appendChild(row);
  scrollBottom();
}

// ── API ──────────────────────────────────────────────────────
async function send(text) {
  setLoading(true);
  appendUserMsg(text);
  appendTyping();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    removeTyping();

    if      (data.type === 'weather') appendWeather(data.data);
    else if (data.type === 'error')   appendText(data.content, true);
    else                              appendText(data.content);
  } catch {
    removeTyping();
    appendText('Could not reach the server. Is the app running?', true);
  } finally {
    setLoading(false);
    textarea.focus();
  }
}

// ── Events ───────────────────────────────────────────────────
form.addEventListener('submit', e => {
  e.preventDefault();
  const text = textarea.value.trim();
  if (!text || isLoading) return;
  textarea.value = '';
  textarea.style.height = 'auto';
  sendBtn.disabled = true;
  send(text);
});

// Enter sends, Shift+Enter = newline
textarea.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.dispatchEvent(new Event('submit'));
  }
});

function attachChips() {
  document.querySelectorAll('.chip').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!isLoading) send(btn.dataset.msg);
    });
  });
}

resetBtn.addEventListener('click', async () => {
  await fetch('/api/reset', { method: 'POST' });
  messagesArea.innerHTML = `
    <div class="welcome" id="welcome">
      <div class="welcome-icon"><i class="fa-solid fa-globe"></i></div>
      <h1>How can I help you today?</h1>
      <p>Ask about weather, time, or anything on your mind.</p>
      <div class="chips">
        <button class="chip" data-msg="What's the weather in Tokyo?">
          <i class="fa-solid fa-cloud-sun"></i><span>Weather in Tokyo</span>
        </button>
        <button class="chip" data-msg="What time is it in New York?">
          <i class="fa-solid fa-clock"></i><span>Time in New York</span>
        </button>
        <button class="chip" data-msg="Compare weather in London and Paris">
          <i class="fa-solid fa-earth-europe"></i><span>Compare cities</span>
        </button>
        <button class="chip" data-msg="Tell me something fascinating about the world">
          <i class="fa-solid fa-lightbulb"></i><span>Fun world fact</span>
        </button>
      </div>
    </div>`;
  attachChips();
});

attachChips();
textarea.focus();
