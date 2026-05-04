const messagesEl = document.getElementById('messages');
const form       = document.getElementById('inputForm');
const input      = document.getElementById('messageInput');
const sendBtn    = document.getElementById('sendBtn');
const resetBtn   = document.getElementById('resetBtn');

let isLoading = false;

// ── Helpers ──────────────────────────────────────────────────

function scrollToBottom() {
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
}

function setLoading(state) {
  isLoading = state;
  sendBtn.disabled = state;
  input.disabled   = state;
}

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatText(text) {
  return escapeHtml(text).replace(/\n/g, '<br>');
}

function weatherIconClass(weatherType) {
  const t = (weatherType || '').toLowerCase();
  if (t.includes('thunder') || t.includes('storm'))              return 'fa-bolt';
  if (t.includes('snow') || t.includes('blizzard'))              return 'fa-snowflake';
  if (t.includes('rain') || t.includes('drizzle') || t.includes('shower')) return 'fa-cloud-rain';
  if (t.includes('fog')  || t.includes('mist')    || t.includes('haze'))   return 'fa-smog';
  if (t.includes('overcast'))                                    return 'fa-cloud';
  if (t.includes('cloud') || t.includes('partly'))               return 'fa-cloud-sun';
  if (t.includes('wind')  || t.includes('breezy'))               return 'fa-wind';
  if (t.includes('sun')   || t.includes('clear'))                return 'fa-sun';
  return 'fa-globe';
}

function formatLocalTime(timeStr) {
  if (!timeStr || timeStr === 'Unavailable') return '—';
  try {
    const d = new Date(timeStr);
    if (isNaN(d)) return timeStr;
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return timeStr;
  }
}

// ── Render ───────────────────────────────────────────────────

function hideWelcome() {
  const w = messagesEl.querySelector('.welcome');
  if (w) w.remove();
}

function appendUserMessage(text) {
  hideWelcome();
  const row = document.createElement('div');
  row.className = 'message-row user';
  row.innerHTML = `
    <div class="avatar user"><i class="fa-solid fa-user"></i></div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
}

function appendTyping() {
  const row = document.createElement('div');
  row.className = 'typing-row';
  row.id = 'typing';
  row.innerHTML = `
    <div class="avatar agent"><i class="fa-solid fa-globe"></i></div>
    <div class="typing-bubble">
      <div class="dot"></div><div class="dot"></div><div class="dot"></div>
    </div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
}

function removeTyping() {
  const t = document.getElementById('typing');
  if (t) t.remove();
}

function appendTextMessage(text, isError = false) {
  const row = document.createElement('div');
  row.className = `message-row ${isError ? 'error' : 'agent'}`;
  row.innerHTML = `
    <div class="avatar agent"><i class="fa-solid fa-globe"></i></div>
    <div class="bubble">${formatText(text)}</div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
}

function buildWeatherCard(item, delay) {
  const card = document.createElement('div');
  card.className = 'weather-card';
  card.style.animationDelay = `${delay}s`;

  if (item.error) {
    card.innerHTML = `
      <div class="weather-error-card">
        <i class="fa-solid fa-circle-exclamation"></i>
        <span>Could not load <strong>${escapeHtml(item.location)}</strong>: ${escapeHtml(item.error)}</span>
      </div>
    `;
    return card;
  }

  const icon      = weatherIconClass(item.weather_type);
  const localTime = formatLocalTime(item.current_time);

  card.innerHTML = `
    <div class="weather-card-header">
      <div class="weather-icon-wrap"><i class="fa-solid ${icon}"></i></div>
      <div>
        <div class="weather-location-name">${escapeHtml(item.location)}</div>
        <div class="weather-desc">${escapeHtml(item.weather_type)}</div>
      </div>
    </div>
    <div class="weather-temp">
      ${escapeHtml(item.temperature_c)}°C
      <span>/ ${escapeHtml(item.temperature_f)}°F</span>
    </div>
    <div class="weather-grid">
      <div class="weather-item">
        <i class="fa-solid fa-droplet"></i>
        <span class="weather-item-label">Humidity</span>
        <span>${escapeHtml(item.humidity_percent)}%</span>
      </div>
      <div class="weather-item">
        <i class="fa-solid fa-clock"></i>
        <span class="weather-item-label">Local</span>
        <span>${localTime}</span>
      </div>
      <div class="weather-item full">
        <i class="fa-solid fa-map-pin"></i>
        <span class="weather-item-label">Timezone</span>
        <span>${escapeHtml(item.timezone)}</span>
      </div>
    </div>
  `;
  return card;
}

function appendWeatherCards(data) {
  const row = document.createElement('div');
  row.className = 'weather-row';

  const avatar = document.createElement('div');
  avatar.className = 'avatar agent';
  avatar.innerHTML = '<i class="fa-solid fa-globe"></i>';

  const cards = document.createElement('div');
  cards.className = 'weather-cards';

  data.forEach((item, i) => cards.appendChild(buildWeatherCard(item, i * 0.07)));

  row.appendChild(avatar);
  row.appendChild(cards);
  messagesEl.appendChild(row);
  scrollToBottom();
}

// ── API ──────────────────────────────────────────────────────

async function sendMessage(message) {
  setLoading(true);
  appendUserMessage(message);
  appendTyping();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    removeTyping();

    if (data.type === 'weather') {
      appendWeatherCards(data.data);
    } else if (data.type === 'error') {
      appendTextMessage(data.content, true);
    } else {
      appendTextMessage(data.content);
    }
  } catch {
    removeTyping();
    appendTextMessage('Could not reach the server. Is the app running?', true);
  } finally {
    setLoading(false);
    input.focus();
  }
}

// ── Events ───────────────────────────────────────────────────

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg || isLoading) return;
  input.value = '';
  sendMessage(msg);
});

resetBtn.addEventListener('click', async () => {
  await fetch('/api/reset', { method: 'POST' });
  messagesEl.innerHTML = '';
  const welcome = document.createElement('div');
  welcome.className = 'welcome';
  welcome.innerHTML = `
    <div class="welcome-icon"><i class="fa-solid fa-globe"></i></div>
    <h2>Hello, I'm World Agent</h2>
    <p>Ask me anything — weather conditions, time zones, or just chat.</p>
    <div class="suggestions">
      <button class="suggestion" data-msg="Weather in Tokyo">
        <i class="fa-solid fa-sun"></i> Weather in Tokyo
      </button>
      <button class="suggestion" data-msg="What time is it in London?">
        <i class="fa-solid fa-clock"></i> Time in London
      </button>
      <button class="suggestion" data-msg="Tell me something interesting about the world">
        <i class="fa-solid fa-earth-americas"></i> Fun world fact
      </button>
    </div>
  `;
  messagesEl.appendChild(welcome);
  attachSuggestions();
});

function attachSuggestions() {
  messagesEl.querySelectorAll('.suggestion').forEach(btn => {
    btn.addEventListener('click', () => {
      const msg = btn.dataset.msg;
      if (msg && !isLoading) sendMessage(msg);
    });
  });
}

attachSuggestions();
input.focus();
