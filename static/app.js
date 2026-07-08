const LLM_STORAGE_KEY = 'ruxi_llm_config';

const PROVIDER_DEFAULTS = {
  doubao: { api_base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-2-0-lite-260428' },
  openai: { api_base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { api_base: '', model: '' },
};

const TAG_COLORS = {
  '影视同人':     { bg: '#EDE9FE', text: '#5B21B6' },
  '你也一定遇到过': { bg: '#FCE7F3', text: '#9D174D' },
  '恋爱':        { bg: '#FEE2E2', text: '#991B1B' },
  '职场':        { bg: '#DBEAFE', text: '#1E40AF' },
  '家庭':        { bg: '#D1FAE5', text: '#065F46' },
  '友情':        { bg: '#FEF3C7', text: '#92400E' },
  '社交':        { bg: '#E0F2FE', text: '#0C4A6E' },
  _default:     { bg: '#F3F4F6', text: '#4B5563' },
};

const state = {
  sessionId: null,
  script: null,
  stats: {},
  turn: 0,
  maxTurns: 15,
  aiName: '',
  playerName: '',
  gameOver: false,
  llmConfigured: false,
  serverHasEnvConfig: false,
  activeTab: 'scripts',
  statsConfig: {},
  currentScriptId: null,
  allScripts: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showScreen(name) {
  $('#screen-select').classList.toggle('hidden', name !== 'select');
  $('#screen-game').classList.toggle('hidden', name !== 'game');
}

function switchTab(tab) {
  state.activeTab = tab;
  $$('.tab-btn').forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('bg-warm-500', active);
    btn.classList.toggle('text-white', active);
    btn.classList.toggle('shadow-sm', active);
    btn.classList.toggle('text-stone-500', !active);
  });
  $$('.tab-panel').forEach((panel) => panel.classList.add('hidden'));
  $(`#tab-${tab}`)?.classList.remove('hidden');
}

function loadStoredLLMConfig() {
  try {
    return JSON.parse(localStorage.getItem(LLM_STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveStoredLLMConfig(config) {
  localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(config));
}

function readLLMForm() {
  return {
    provider: $('#cfg-provider').value,
    api_base: $('#cfg-api-base').value.trim(),
    api_key: $('#cfg-api-key').value.trim(),
    model: $('#cfg-model').value.trim(),
  };
}

function fillLLMForm(config) {
  if (!config) return;
  $('#cfg-provider').value = config.provider || 'doubao';
  $('#cfg-api-base').value = config.api_base || '';
  $('#cfg-api-key').value = config.api_key || '';
  $('#cfg-model').value = config.model || '';
}

function getEffectiveLLMConfig() {
  const stored = loadStoredLLMConfig();
  if (stored?.api_key && stored?.api_base && stored?.model) return stored;
  if (state.serverHasEnvConfig) return null;
  return null;
}

function updateConfigUI() {
  const configured = state.llmConfigured;
  $('#config-warning')?.classList.toggle('hidden', configured);
  const status = $('#cfg-status');
  if (!status) return;
  if (configured) {
    status.className = 'rounded-xl px-3 py-2 text-xs bg-emerald-50 text-emerald-700 border border-emerald-100';
    status.textContent = state.serverHasEnvConfig && !loadStoredLLMConfig()?.api_key
      ? '已就绪：使用服务端环境变量配置'
      : '已就绪：使用本地保存的配置';
    status.classList.remove('hidden');
  } else {
    status.className = 'rounded-xl px-3 py-2 text-xs bg-amber-50 text-amber-700 border border-amber-100';
    status.textContent = '尚未配置：请填写 Provider、API Key 和 Model';
    status.classList.remove('hidden');
  }
}

async function refreshLLMStatus() {
  try {
    const res = await fetch('/api/config/llm');
    const data = await res.json();
    state.serverHasEnvConfig = data.configured && data.source === 'env';
    const local = loadStoredLLMConfig();
    state.llmConfigured = Boolean(
      (local?.api_key && local?.api_base && local?.model) || data.configured
    );
    if (!local && data.configured) {
      fillLLMForm({
        provider: data.provider,
        api_base: data.api_base,
        model: data.model,
        api_key: '',
      });
    }
    updateConfigUI();
  } catch (err) {
    console.error(err);
  }
}

function onProviderChange() {
  const provider = $('#cfg-provider').value;
  const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.custom;
  if (provider !== 'custom') {
    $('#cfg-api-base').value = defaults.api_base;
    if (!$('#cfg-model').value || Object.values(PROVIDER_DEFAULTS).some((d) => d.model === $('#cfg-model').value)) {
      $('#cfg-model').value = defaults.model;
    }
  }
}

function showCfgMessage(text, ok = true) {
  const status = $('#cfg-status');
  status.className = `rounded-xl px-3 py-2 text-xs ${ok ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-red-50 text-red-600 border border-red-100'}`;
  status.textContent = text;
  status.classList.remove('hidden');
}

function statBarFill(value, cfg = {}) {
  const max = cfg.max ?? 100;
  const direction = cfg.direction ?? 'lower_is_better';
  const ratio = value / max;
  const severity = direction === 'lower_is_better' ? ratio : (1 - ratio);
  if (severity < 0.3) return '#C0DD97';
  if (severity < 0.7) return '#BA7517';
  return '#E24B4A';
}

function renderStats(changes = {}) {
  const container = $('#stats-bar');
  container.innerHTML = '';

  for (const [name, value] of Object.entries(state.stats)) {
    const cfg = state.statsConfig[name] || {};
    const block = document.createElement('div');

    const labels = document.createElement('div');
    labels.className = 'stat-row-labels';
    labels.innerHTML = `<span>${name}</span><span>${value}${changes[name] ? ` (${changes[name] > 0 ? '+' : ''}${changes[name]})` : ''}</span>`;

    const track = document.createElement('div');
    track.className = 'stat-track';
    const fill = document.createElement('div');
    fill.className = 'stat-fill';
    fill.style.width = `${value}%`;
    fill.style.height = '100%';
    fill.style.borderRadius = '3px';
    fill.style.background = statBarFill(value, cfg);
    track.appendChild(fill);

    block.appendChild(labels);
    block.appendChild(track);
    container.appendChild(block);
  }
}

function updateTurnIndicator() {
  $('#turn-indicator').textContent = `第 ${state.turn}/${state.maxTurns} 轮`;
}

function scrollChatToBottom() {
  const area = $('#chat-area');
  area.scrollTop = area.scrollHeight;
}

function renderEmotionTag(nameEl, tag) {
  const existing = nameEl.querySelector('.emotion-tag');
  if (existing) existing.remove();
  if (!tag) return;
  const badge = document.createElement('span');
  badge.className = 'emotion-tag';
  badge.textContent = tag;
  nameEl.appendChild(badge);
}

function createMessageBubble(role, character) {
  const wrapper = document.createElement('div');
  wrapper.className = `msg-enter msg-row ${role === 'user' ? 'user' : 'ai'}`;

  const nameEl = document.createElement('p');
  nameEl.className = `msg-name ${role === 'user' ? 'user-name' : ''}`;
  nameEl.textContent = character;

  const bubble = document.createElement('div');
  bubble.className = role === 'user' ? 'bubble-user' : 'bubble-ai';

  const text = document.createElement('p');
  text.style.margin = '0';
  text.className = role === 'assistant' ? '' : '';
  bubble.appendChild(text);

  if (role === 'assistant') {
    wrapper.appendChild(nameEl);
    wrapper.appendChild(bubble);
  } else {
    wrapper.appendChild(bubble);
    wrapper.appendChild(nameEl);
  }

  return { wrapper, text, nameEl };
}

function appendMessage(role, content, character, emotionTag = '') {
  const area = $('#chat-area');
  const { wrapper, text, nameEl } = createMessageBubble(role, character);
  text.textContent = content;
  if (role === 'assistant' && emotionTag) renderEmotionTag(nameEl, emotionTag);
  area.appendChild(wrapper);
  scrollChatToBottom();
}

function appendTypingBubble(character) {
  const area = $('#chat-area');
  const { wrapper, text, nameEl } = createMessageBubble('assistant', character);
  wrapper.dataset.typing = 'true';
  text.innerHTML = '<span class="typing-dots-v1 inline-flex gap-1"><span></span><span></span><span></span></span>';
  area.appendChild(wrapper);
  scrollChatToBottom();
  return { wrapper, text, nameEl };
}

function promoteTypingBubbleToStream(bubbleRef) {
  const { wrapper, text, nameEl } = bubbleRef;
  delete wrapper.dataset.typing;
  text.textContent = '';
  text.classList.add('streaming-text');
  return { wrapper, text, nameEl };
}

function showEnding(outcome, text) {
  const isWin = outcome === 'win';
  const iconWrap = $('#ending-icon-wrap');
  iconWrap.className = `ending-icon-wrap ${isWin ? 'win' : 'lose'}`;
  iconWrap.textContent = isWin ? '✓' : '✕';

  const titles = state.script?.ending_titles || {};
  const outcomeLabel = isWin ? '达成' : '失败';
  $('#ending-meta').textContent = `第 ${state.turn} / ${state.maxTurns} 轮 · ${outcomeLabel}`;
  $('#ending-title').textContent = isWin
    ? (titles.win || '达成目标')
    : (titles.lose || '未能达成目标');
  $('#ending-text').textContent = text || (isWin ? '你成功化解了矛盾！' : '未能达成目标，再试一次吧。');

  const statsEl = $('#ending-stats');
  statsEl.innerHTML = '';
  for (const [name, value] of Object.entries(state.stats)) {
    const item = document.createElement('div');
    item.className = 'ending-stat-item';
    item.innerHTML = `<p>最终${name}</p><strong>${value}</strong>`;
    statsEl.appendChild(item);
  }

  $('#ending-overlay').classList.remove('hidden');
  $('#input-area').classList.add('hidden');
}

function hideEnding() {
  $('#ending-overlay').classList.add('hidden');
  $('#input-area').classList.remove('hidden');
}

function resetToSelect() {
  state.sessionId = null;
  state.script = null;
  state.stats = {};
  state.turn = 0;
  state.gameOver = false;

  hideEnding();
  $('#chat-area').innerHTML = '';
  $('#stats-bar').innerHTML = '';
  $('#message-input').value = '';
  $('#send-btn').disabled = false;
  switchTab('scripts');
  showScreen('select');
  loadScripts();
  refreshLLMStatus();
}

function parseSSEChunk(buffer) {
  const events = [];
  const parts = buffer.split('\n\n');
  const rest = parts.pop() || '';
  for (const part of parts) {
    const line = part.split('\n').find((l) => l.startsWith('data: '));
    if (line) {
      try {
        events.push(JSON.parse(line.slice(6)));
      } catch (_) { /* ignore partial */ }
    }
  }
  return { events, rest };
}

const CATEGORY_META = [
  {
    origin_tag: '影视同人',
    display: '影视热梗',
    subtitle: '这一世由你夺回一切',
  },
  {
    origin_tag: '你也一定遇到过',
    display: '你也一定遇到过',
    subtitle: '如何炼就一张好嘴',
  },
];

function tagBadgeEl(tag) {
  const c = TAG_COLORS[tag] || TAG_COLORS._default;
  const span = document.createElement('span');
  span.textContent = tag;
  span.style.cssText = `background:${c.bg};color:${c.text};display:inline-block;font-size:10px;font-weight:500;padding:2px 8px;border-radius:999px;`;
  return span;
}

function buildScriptCard(script) {
  const card = document.createElement('button');
  card.className = 'w-full text-left bg-white rounded-2xl p-4 border border-warm-100 hover:border-warm-300 transition group';
  card.style.cssText = 'border-width:0.5px;';

  const tags = document.createElement('div');
  tags.style.cssText = 'display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px;';
  if (script.origin_tag) tags.appendChild(tagBadgeEl(script.origin_tag));
  for (const t of (script.theme_tags || [])) tags.appendChild(tagBadgeEl(t));
  card.appendChild(tags);

  const title = document.createElement('h3');
  title.style.cssText = 'font-size:15px;font-weight:500;color:#1c1917;margin-bottom:5px;letter-spacing:0.01em;';
  title.textContent = script.title;
  card.appendChild(title);

  if (script.teaser) {
    const teaser = document.createElement('p');
    teaser.style.cssText = 'font-size:12.5px;color:#78716c;line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:10px;';
    teaser.textContent = script.teaser;
    card.appendChild(teaser);
  }

  const bottom = document.createElement('div');
  bottom.style.cssText = 'display:flex;justify-content:space-between;align-items:center;';
  bottom.innerHTML = `
    <span style="font-size:11px;color:#a8a29e;">${script.player_role_hint || ''}</span>
    <span style="font-size:11px;color:#a8a29e;">${script.estimated_turns_hint || ''}</span>
  `;
  card.appendChild(bottom);

  card.addEventListener('click', () => showScriptModal(script.id));
  return card;
}

function renderScriptList() {
  const list = $('#script-list');
  list.innerHTML = '';

  if (!state.allScripts.length) {
    list.innerHTML = '<p class="text-center text-stone-400 py-8 text-sm">暂无可用剧本</p>';
    return;
  }

  // Group scripts by origin_tag, preserving CATEGORY_META order
  const grouped = new Map();
  for (const meta of CATEGORY_META) grouped.set(meta.origin_tag, []);
  for (const s of state.allScripts) {
    if (!grouped.has(s.origin_tag)) grouped.set(s.origin_tag, []);
    grouped.get(s.origin_tag).push(s);
  }

  for (const [originTag, scripts] of grouped) {
    if (!scripts.length) continue;
    const meta = CATEGORY_META.find(m => m.origin_tag === originTag);
    const displayName = meta ? meta.display : originTag;
    const subtitle = meta ? meta.subtitle : '';
    const catId = 'cat-' + originTag.replace(/\s/g, '_');

    const section = document.createElement('div');
    section.className = 'script-category';
    section.id = catId;

    section.innerHTML = `
      <div class="script-category-header" onclick="document.getElementById('${catId}').classList.toggle('collapsed')">
        <div>
          <div class="script-category-name">${displayName}</div>
          ${subtitle ? `<div class="script-category-subtitle">${subtitle}</div>` : ''}
        </div>
        <div class="script-category-meta">
          <span class="script-category-count">${scripts.length} 个剧本</span>
          <svg class="script-category-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>
      <div class="script-category-cards">
        <div class="script-category-inner"></div>
      </div>
    `;

    const inner = section.querySelector('.script-category-inner');
    for (const script of scripts) inner.appendChild(buildScriptCard(script));

    list.appendChild(section);
  }
}

// ── Briefing Modal ──────────────────────────────────────────────

let _briefingScriptId = null;

function showBriefingStep(n) {
  $('#briefing-step-1').classList.toggle('hidden', n !== 1);
  $('#briefing-step-2').classList.toggle('hidden', n !== 2);
  document.querySelectorAll('.briefing-step').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.step) === n);
  });
}

async function showScriptModal(scriptId) {
  if (!state.llmConfigured) {
    switchTab('settings');
    updateConfigUI();
    return;
  }

  _briefingScriptId = scriptId;

  let detail;
  try {
    const res = await fetch(`/api/scripts/${scriptId}/detail`);
    if (!res.ok) throw new Error('Failed to load script detail');
    detail = await res.json();
  } catch (err) {
    console.error(err);
    alert('加载剧本信息失败，请重试');
    return;
  }

  // Step 1: briefing
  $('#briefing-script-title').textContent = detail.title;
  $('#briefing-text').textContent = detail.briefing;
  $('#briefing-objective').textContent = detail.objective;

  // Step 2: character intro
  $('#briefing-ai-name').textContent = detail.ai_character.name;
  $('#briefing-ai-intro').textContent = detail.ai_character.intro;

  // AI character customization: only for 你也一定遇到过
  const isOriginal = detail.origin_tag === '你也一定遇到过';
  $('#briefing-ai-setup').classList.toggle('hidden', !isOriginal);
  if (isOriginal) {
    $('#briefing-ai-name-input').value = '';
    $('#briefing-ai-name-input').placeholder = `默认：${detail.ai_character.name}`;
    $('#briefing-ai-persona').value = '';
    $('#briefing-ai-persona').placeholder = '不填则使用默认设定';
  }

  showBriefingStep(1);
  $('#briefing-overlay').classList.remove('hidden');
}

function hideBriefingModal() {
  $('#briefing-overlay').classList.add('hidden');
  _briefingScriptId = null;
}

async function confirmStartGame() {
  const scriptId = _briefingScriptId;
  if (!scriptId) return;

  const isOriginal = !$('#briefing-ai-setup').classList.contains('hidden');
  let aiName = null;
  let aiPersona = null;

  if (isOriginal) {
    const nameVal = $('#briefing-ai-name-input').value.trim();
    const personaVal = $('#briefing-ai-persona').value.trim();
    if (nameVal) aiName = nameVal;
    if (personaVal) aiPersona = personaVal;
  }

  hideBriefingModal();
  await startGame(scriptId, aiName, aiPersona);
}

$('#briefing-cancel-btn').addEventListener('click', hideBriefingModal);
$('#briefing-next-btn').addEventListener('click', () => showBriefingStep(2));
$('#briefing-back-btn').addEventListener('click', () => showBriefingStep(1));
$('#briefing-start-btn').addEventListener('click', confirmStartGame);
$('#briefing-overlay').addEventListener('click', (e) => {
  if (e.target === $('#briefing-overlay')) hideBriefingModal();
});

// ── Scripts ─────────────────────────────────────────────────────

async function startGame(scriptId, aiName = null, aiPersona = null) {
  if (!state.llmConfigured) {
    switchTab('settings');
    updateConfigUI();
    return;
  }

  hideEnding();
  const llmConfig = getEffectiveLLMConfig();
  const payload = { script_id: scriptId };
  if (llmConfig) payload.llm_config = llmConfig;
  if (aiName) payload.ai_name = aiName;
  if (aiPersona) payload.ai_persona = aiPersona;

  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start session');
    }
    const data = await res.json();

    state.sessionId = data.session_id;
    state.script = data.script;
    state.stats = data.stats;
    state.turn = data.turn;
    state.maxTurns = data.script.max_turns;
    state.aiName = data.script.ai_character_name;
    state.playerName = data.script.player_character_name;
    state.statsConfig = data.script.stats_config || {};
    state.currentScriptId = scriptId;
    state.gameOver = false;

    $('#game-title').textContent = data.script.title;
    $('#game-objective').textContent = `目标：${data.script.objective}`;
    $('#chat-area').innerHTML = '';
    hideEnding();

    renderStats();
    updateTurnIndicator();
    appendMessage('assistant', data.opening_line, state.aiName);

    showScreen('game');
    $('#message-input').focus();
  } catch (err) {
    alert('启动游戏失败，请重试');
    console.error(err);
  }
}

async function sendMessage(message) {
  if (!message.trim() || state.gameOver) return;

  appendMessage('user', message, state.playerName);
  $('#message-input').value = '';
  $('#send-btn').disabled = true;

  const typingBubble = appendTypingBubble(state.aiName);
  let streamBubble = null;

  try {
    const res = await fetch('/api/session/message/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, message }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Request failed');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let gotToken = false;
    let finalData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSSEChunk(buffer);
      buffer = rest;

      for (const event of events) {
        if (event.type === 'emotion_tag') {
          if (!gotToken) {
            streamBubble = promoteTypingBubbleToStream(typingBubble);
            gotToken = true;
          }
          renderEmotionTag(streamBubble.nameEl, event.emotion_tag);
        } else if (event.type === 'token') {
          if (!gotToken) {
            streamBubble = promoteTypingBubbleToStream(typingBubble);
            gotToken = true;
          }
          streamBubble.text.textContent += event.content;
          scrollChatToBottom();
        } else if (event.type === 'done') {
          finalData = event;
        }
      }
    }

    if (!finalData) throw new Error('Stream ended without result');

    if (finalData.game_over) {
      if (typingBubble?.wrapper?.parentNode) typingBubble.wrapper.remove();
      if (streamBubble?.wrapper?.parentNode) streamBubble.wrapper.remove();
    } else if (!gotToken) {
      typingBubble.wrapper.remove();
      appendMessage('assistant', finalData.reply, state.aiName, finalData.emotion_tag || '');
    } else {
      streamBubble.text.classList.remove('streaming-text');
      if (finalData.reply && streamBubble.text.textContent !== finalData.reply) {
        streamBubble.text.textContent = finalData.reply;
      }
      renderEmotionTag(streamBubble.nameEl, finalData.emotion_tag || '');
    }

    state.stats = finalData.stats;
    state.turn = finalData.turn;
    renderStats(finalData.stat_changes || {});
    updateTurnIndicator();

    if (finalData.game_over) {
      state.gameOver = true;
      showEnding(finalData.outcome || finalData.result, finalData.ending_text);
    }
  } catch (err) {
    if (typingBubble?.wrapper?.parentNode) {
      typingBubble.wrapper.remove();
    }
    appendMessage('assistant', '（系统暂时无法响应，请稍后再试。）', state.aiName);
    console.error(err);
  } finally {
    $('#send-btn').disabled = false;
    if (!state.gameOver) $('#message-input').focus();
  }
}

$('#message-form').addEventListener('submit', (e) => {
  e.preventDefault();
  sendMessage($('#message-input').value);
});

$('#help-btn').addEventListener('click', () => {
  alert('提示功能即将上线，敬请期待。');
});

$('#exit-game-btn').addEventListener('click', () => {
  state.sessionId = null;
  state.gameOver = false;
  showScreen('select');
});

$('#replay-btn').addEventListener('click', () => {
  if (state.currentScriptId) startGame(state.currentScriptId);
});

$('#change-script-btn').addEventListener('click', resetToSelect);

$$('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

$$('[data-tab-link]').forEach((el) => {
  el.addEventListener('click', () => switchTab(el.dataset.tabLink));
});

$('#cfg-provider').addEventListener('change', onProviderChange);

$('#llm-config-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const config = readLLMForm();
  if (!config.api_base || !config.api_key || !config.model) {
    showCfgMessage('请完整填写 API Base、API Key 和 Model', false);
    return;
  }
  saveStoredLLMConfig(config);
  state.llmConfigured = true;
  updateConfigUI();
  showCfgMessage('配置已保存');
});

$('#cfg-test-btn').addEventListener('click', async () => {
  const config = readLLMForm();
  if (!config.api_base || !config.api_key || !config.model) {
    showCfgMessage('请完整填写后再测试', false);
    return;
  }
  $('#cfg-test-btn').disabled = true;
  showCfgMessage('正在测试连接…', true);
  try {
    const res = await fetch('/api/config/llm/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '测试失败');
    showCfgMessage(`连接成功 · ${data.model} · ${data.preview}`);
  } catch (err) {
    showCfgMessage(err.message || '连接失败', false);
  } finally {
    $('#cfg-test-btn').disabled = false;
  }
});

fillLLMForm(loadStoredLLMConfig() || { provider: 'doubao', ...PROVIDER_DEFAULTS.doubao, api_key: '' });
switchTab('scripts');
Promise.all([refreshLLMStatus(), fetch('/api/scripts').then(r => r.json())]).then(([, data]) => {
  state.allScripts = (data && data.scripts) || [];
  renderScriptList();
});
