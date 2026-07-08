const LLM_STORAGE_KEY = 'ruxi_llm_config';

const PROVIDER_DEFAULTS = {
  doubao: { api_base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-2-0-lite-260428' },
  openai: { api_base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { api_base: '', model: '' },
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

function promoteTypingBubbleToStream(bubbleRef, character) {
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

async function loadScripts() {
  const res = await fetch('/api/scripts');
  const data = await res.json();
  const list = $('#script-list');
  list.innerHTML = '';

  if (!data.scripts.length) {
    list.innerHTML = '<p class="text-center text-stone-400">暂无可用剧本</p>';
    return;
  }

  for (const script of data.scripts) {
    const card = document.createElement('button');
    card.className = 'w-full text-left bg-white/80 hover:bg-white rounded-2xl p-5 shadow-sm border border-warm-100 hover:border-warm-300 hover:shadow-md transition group';
    card.innerHTML = `
      <h3 class="text-lg font-semibold text-warm-600 group-hover:text-warm-700">${script.title}</h3>
      <p class="mt-2 text-sm text-stone-500 line-clamp-2">${script.objective}</p>
      <span class="inline-block mt-3 text-xs text-warm-500 font-medium">点击开始 →</span>
    `;
    card.addEventListener('click', () => startGame(script.id));
    list.appendChild(card);
  }
}

async function startGame(scriptId) {
  if (!state.llmConfigured) {
    switchTab('settings');
    updateConfigUI();
    return;
  }

  hideEnding();
  const llmConfig = getEffectiveLLMConfig();
  const payload = { script_id: scriptId };
  if (llmConfig) payload.llm_config = llmConfig;

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
            streamBubble = promoteTypingBubbleToStream(typingBubble, state.aiName);
            gotToken = true;
          }
          renderEmotionTag(streamBubble.nameEl, event.emotion_tag);
        } else if (event.type === 'token') {
          if (!gotToken) {
            streamBubble = promoteTypingBubbleToStream(typingBubble, state.aiName);
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

    if (!gotToken) {
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
refreshLLMStatus().then(loadScripts);
