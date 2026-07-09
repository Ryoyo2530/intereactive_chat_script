const LLM_STORAGE_KEY = 'ruxi_llm_config';

const PROVIDER_DEFAULTS = {
  doubao: { api_base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-2-0-lite-260428' },
  openai: { api_base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { api_base: '', model: '' },
};

/** Tag palette — low-saturation, aligned with Echoes paper/sage/terracotta tokens */
const TAG_COLORS = {
  '影视同人':     { bg: '#EDE8DF', text: '#5C4A3A', border: '#D5CEC3' },
  '你也一定遇到过': { bg: '#E8ECE8', text: '#4B6355', border: '#C8D4CA' },
  '恋爱':        { bg: '#EDE3DF', text: '#8A4D4A', border: '#D9C8C4' },
  '职场':        { bg: '#E6EAE6', text: '#3D5247', border: '#C5CCC6' },
  '家庭':        { bg: '#EBE8E3', text: '#6B5E52', border: '#D5D0C8' },
  '友情':        { bg: '#E5EBE6', text: '#4A5F4F', border: '#C2D0C6' },
  '社交':        { bg: '#EAE6E1', text: '#7A6A5C', border: '#D4CCC2' },
  _default:     { bg: '#EDEAE4', text: '#8A8578', border: '#DDD8CF' },
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
    btn.classList.toggle('is-active', btn.dataset.tab === tab);
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
    status.style.color = 'var(--echo-accent)';
    status.textContent = state.serverHasEnvConfig && !loadStoredLLMConfig()?.api_key
      ? '已就绪：使用服务端环境变量配置'
      : '已就绪：使用本地保存的配置';
    status.classList.remove('hidden');
  } else {
    status.style.color = 'var(--echo-danger)';
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
  status.style.color = ok ? 'var(--echo-accent)' : 'var(--echo-danger)';
  status.textContent = text;
  status.classList.remove('hidden');
}

function tagBadgeEl(tag) {
  const c = TAG_COLORS[tag] || TAG_COLORS._default;
  const span = document.createElement('span');
  span.className = 'echoes-tag echoes-tag-colored';
  span.textContent = tag;
  span.style.background = c.bg;
  span.style.color = c.text;
  span.style.borderColor = c.border;
  return span;
}

function buildScriptCard(script) {
  const card = document.createElement('button');
  card.className = 'echoes-script-card';

  const tags = document.createElement('div');
  tags.className = 'echoes-script-card-tags';
  if (script.origin_tag) tags.appendChild(tagBadgeEl(script.origin_tag));
  for (const t of (script.theme_tags || [])) tags.appendChild(tagBadgeEl(t));
  if (tags.childNodes.length) card.appendChild(tags);

  const title = document.createElement('h3');
  title.className = 'echoes-script-card-title';
  title.textContent = script.title;
  card.appendChild(title);

  if (script.teaser) {
    const teaser = document.createElement('p');
    teaser.className = 'echoes-script-card-teaser';
    teaser.textContent = script.teaser;
    card.appendChild(teaser);
  }

  const bottom = document.createElement('div');
  bottom.className = 'echoes-script-card-meta';
  bottom.innerHTML = `
    <span>${script.player_role_hint || ''}</span>
    <span>${script.estimated_turns_hint || ''}</span>
  `;
  card.appendChild(bottom);

  card.addEventListener('click', () => showScriptModal(script.id));
  return card;
}

function showEnding(outcome, text, turn, maxTurns) {
  const isWin = outcome === 'win';
  const titles = state.script?.ending_titles || {};
  const outcomeLabel = isWin ? '达成' : '失败';
  $('#ending-meta').textContent = `第 ${turn ?? state.turn} / ${maxTurns ?? state.maxTurns} 轮 · ${outcomeLabel}`;
  $('#ending-title').textContent = isWin
    ? (titles.win || '达成目标')
    : (titles.lose || '未能达成目标');
  $('#ending-text').textContent = text || (isWin ? '你成功化解了矛盾！' : '未能达成目标，再试一次吧。');

  const statsEl = $('#ending-stats');
  statsEl.innerHTML = '';
  for (const [name, value] of Object.entries(state.stats)) {
    const item = document.createElement('div');
    item.className = 'echoes-ending-stat';
    item.innerHTML = `<span>最终${name}</span><strong>${value}</strong>`;
    statsEl.appendChild(item);
  }

  $('#ending-overlay').classList.remove('hidden');
  $('#echoes-input-area')?.classList.add('hidden');
}

function hideEnding() {
  $('#ending-overlay').classList.add('hidden');
  $('#echoes-input-area')?.classList.remove('hidden');
}

function resetToSelect() {
  state.sessionId = null;
  state.script = null;
  state.stats = {};
  state.turn = 0;
  state.gameOver = false;

  window.dispatchEvent(new CustomEvent('echoes:reset'));
  hideEnding();
  switchTab('scripts');
  showScreen('select');
  loadScripts();
  refreshLLMStatus();
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

function renderScriptList() {
  const list = $('#script-list');
  list.innerHTML = '';

  if (!state.allScripts.length) {
    list.innerHTML = '<p class="echoes-select-sub text-center py-8">暂无可用剧本</p>';
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
let _briefingDetail = null;

function showBriefingStep(n) {
  $('#briefing-step-1').classList.toggle('hidden', n !== 1);
  $('#briefing-step-2').classList.toggle('hidden', n !== 2);
  document.querySelectorAll('.briefing-step').forEach(el => {
    const active = Number(el.dataset.step) === n;
    el.classList.toggle('active', active);
    el.classList.toggle('is-active', active);
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

  _briefingDetail = detail;
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
  _briefingDetail = null;
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

  const scriptDetail = _briefingDetail;
  hideBriefingModal();
  await startGame(scriptId, aiName, aiPersona, scriptDetail);
}

$('#briefing-cancel-btn').addEventListener('click', hideBriefingModal);
$('#briefing-next-btn').addEventListener('click', () => showBriefingStep(2));
$('#briefing-back-btn').addEventListener('click', () => showBriefingStep(1));
$('#briefing-start-btn').addEventListener('click', confirmStartGame);
$('#briefing-overlay').addEventListener('click', (e) => {
  if (e.target === $('#briefing-overlay')) hideBriefingModal();
});

async function startGame(scriptId, aiName = null, aiPersona = null, scriptDetail = null) {
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

    hideEnding();
    showScreen('game');
    window.dispatchEvent(new CustomEvent('echoes:session-started', {
      detail: { ...data, scriptDetail },
    }));
  } catch (err) {
    alert('启动游戏失败，请重试');
    console.error(err);
  }
}

window.addEventListener('echoes:game-over', (e) => {
  const d = e.detail || {};
  state.gameOver = true;
  state.stats = d.stats || state.stats;
  state.turn = d.turn ?? state.turn;
  showEnding(d.outcome, d.ending_text, d.turn, d.maxTurns);
});

window.addEventListener('echoes:exit', () => {
  state.sessionId = null;
  state.gameOver = false;
  window.dispatchEvent(new CustomEvent('echoes:reset'));
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
