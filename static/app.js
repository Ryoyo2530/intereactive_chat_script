import {
  SITE_CREDIT,
  creditLine,
  performanceId,
  buildShareCopy,
  exportEssenceImage,
  exportFullImage,
  exportTranscript,
  shareOrDownload,
  copyText,
} from '/share/share-capture.js?v=4';

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
  statsConfig: {},
  currentScriptId: null,
  allScripts: [],
  authorized: false,
  lastEnding: null,
  flowEntries: [],
  perfId: '',
  playMode: 'short_form',
  pendingSaveId: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showScreen(name) {
  $('#screen-select').classList.toggle('hidden', name !== 'select');
  $('#screen-game').classList.toggle('hidden', name !== 'game');
  $('#settings-open-btn')?.classList.toggle('hidden', name !== 'select');
  if (name !== 'select') closeSettings();
}

function showInviteGate(show) {
  $('#invite-gate')?.classList.toggle('hidden', !show);
  if (show) {
    $('#settings-open-btn')?.classList.add('hidden');
    closeSettings();
  } else if (!$('#screen-select')?.classList.contains('hidden')) {
    $('#settings-open-btn')?.classList.remove('hidden');
  }
}

function openSettings() {
  updateConfigUI();
  $('#settings-overlay')?.classList.remove('hidden');
  document.body.classList.add('echoes-settings-open');
}

function closeSettings() {
  $('#settings-overlay')?.classList.add('hidden');
  document.body.classList.remove('echoes-settings-open');
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
  const isLong = (script.work_type || 'short_form') === 'long_form';
  const card = document.createElement('button');
  card.className = 'echoes-script-card' + (isLong ? ' echoes-script-card-long' : '');

  // 特写：顶部保留 origin + theme 徽章；长镜：不与特写共享标签体系，tag 只在卡片底部
  if (!isLong) {
    const tags = document.createElement('div');
    tags.className = 'echoes-script-card-tags';
    if (script.origin_tag) tags.appendChild(tagBadgeEl(script.origin_tag));
    for (const t of (script.theme_tags || [])) tags.appendChild(tagBadgeEl(t));
    if (tags.childNodes.length) card.appendChild(tags);
  }

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

  if (isLong) {
    const status = script.progress_status || 'not_started';
    // Progress dots only when started (avoids revealing chapter count)
    if (status !== 'not_started' && script.chapter_count) {
      const dots = document.createElement('div');
      dots.className = 'chapter-dots';
      const visited = Math.min(script.visited_count || 0, script.chapter_count);
      for (let i = 0; i < script.chapter_count; i++) {
        if (i > 0) {
          const connector = document.createElement('span');
          connector.className = 'dot-connector';
          dots.appendChild(connector);
        }
        const dot = document.createElement('span');
        dot.className = 'dot ' + (i < visited ? 'filled' : 'hollow');
        dots.appendChild(dot);
      }
      card.appendChild(dots);
    }

    const bottom = document.createElement('div');
    bottom.className = 'echoes-script-card-meta';
    let left = '未开始';
    if (status === 'in_progress') {
      const idx = script.current_chapter_index || script.visited_count || 1;
      left = `进行中 · 第${idx}幕`;
    } else if (status === 'completed') {
      left = '已完结';
    }
    const endingLabel = script.all_endings_discovered ? '已阅尽此世' : '仍有未至之地';
    bottom.innerHTML = `
      <span>${left}</span>
      <span class="ending-status">
        <svg class="ending-status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        ${endingLabel}
      </span>
    `;
    card.appendChild(bottom);

    const themeTags = script.theme_tags || [];
    if (themeTags.length) {
      const foot = document.createElement('div');
      foot.className = 'echoes-script-card-foot-tags';
      for (const t of themeTags) foot.appendChild(tagBadgeEl(t));
      card.appendChild(foot);
    }
  } else {
    const bottom = document.createElement('div');
    bottom.className = 'echoes-script-card-meta';
    bottom.innerHTML = `
      <span>${script.player_role_hint || ''}</span>
      <span>${script.estimated_turns_hint || ''}</span>
    `;
    card.appendChild(bottom);
  }

  card.addEventListener('click', () => {
    state.pendingSaveId = (isLong && script.save_id && script.progress_status === 'in_progress')
      ? script.save_id
      : null;
    showScriptModal(script.id);
  });
  return card;
}

function scriptsForCurrentMode() {
  return (state.allScripts || []).filter((s) => {
    const t = s.work_type || 'short_form';
    return t === state.playMode;
  });
}

function bindModeSwitch() {
  const root = $('#mode-switch');
  if (!root) return;
  root.querySelectorAll('[data-mode]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      if (!mode || mode === state.playMode) return;
      state.playMode = mode;
      root.querySelectorAll('[data-mode]').forEach((b) => {
        const on = b.getAttribute('data-mode') === mode;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      renderScriptList();
    });
  });
}

function fillSiteCredit() {
  const creditEl = $('#site-credit-line');
  if (creditEl) creditEl.textContent = creditLine();

  const endingCredit = $('#ending-credit');
  if (endingCredit) endingCredit.textContent = creditLine();

  const disclaimer = $('#ending-disclaimer');
  if (disclaimer) {
    disclaimer.textContent = `${SITE_CREDIT.disclaimer} · ${SITE_CREDIT.fanficNote}`;
  }

  const feedback = $('#footer-feedback-line');
  if (feedback) {
    if (SITE_CREDIT.feedbackUrl) {
      feedback.innerHTML = `<a href="${SITE_CREDIT.feedbackUrl}" target="_blank" rel="noopener noreferrer">${SITE_CREDIT.feedbackLabel}</a>`;
    } else {
      feedback.textContent = `${SITE_CREDIT.feedbackLabel} · ${SITE_CREDIT.contact}`;
    }
  }
}

function showEnding(outcome, text, turn, maxTurns, extra = {}) {
  const isWin = outcome === 'win';
  const titles = state.script?.ending_titles || {};
  const outcomeLabel = isWin ? '达成' : '失败';
  const endingTitle = isWin
    ? (titles.win || '达成目标')
    : (titles.lose || '未能达成目标');
  const endingText = text || (isWin ? '你成功化解了矛盾！' : '未能达成目标，再试一次吧。');

  $('#ending-meta').textContent = `第 ${turn ?? state.turn} / ${maxTurns ?? state.maxTurns} 轮 · ${outcomeLabel}`;
  $('#ending-title').textContent = endingTitle;
  $('#ending-text').textContent = endingText;

  const statsEl = $('#ending-stats');
  statsEl.innerHTML = '';
  for (const [name, value] of Object.entries(state.stats)) {
    const item = document.createElement('div');
    item.className = 'echoes-ending-stat';
    item.innerHTML = `<span>最终${name}</span><strong>${value}</strong>`;
    statsEl.appendChild(item);
  }

  state.perfId = performanceId(state.script?.id || state.currentScriptId);
  $('#ending-perf-id').textContent = state.perfId;

  state.lastEnding = {
    outcome,
    endingTitle,
    endingText,
    turn: turn ?? state.turn,
    maxTurns: maxTurns ?? state.maxTurns,
  };
  state.flowEntries = extra.entries || state.flowEntries || [];

  fillSiteCredit();
  $('#share-status')?.setAttribute('hidden', '');
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
  state.lastEnding = null;
  state.flowEntries = [];

  window.dispatchEvent(new CustomEvent('echoes:reset'));
  hideEnding();
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

  const filtered = scriptsForCurrentMode();
  if (!filtered.length) {
    const empty = state.playMode === 'long_form'
      ? '长镜作品筹备中，先去特写走一程吧。'
      : '暂无可用剧本';
    list.innerHTML = `<p class="echoes-select-sub text-center py-8">${empty}</p>`;
    return;
  }

  // 长镜：不与特写共享 origin_tag 分类体系，直接平铺卡片
  if (state.playMode === 'long_form') {
    const stack = document.createElement('div');
    stack.className = 'longform-script-stack';
    for (const script of filtered) stack.appendChild(buildScriptCard(script));
    list.appendChild(stack);
    return;
  }

  const grouped = new Map();
  for (const meta of CATEGORY_META) grouped.set(meta.origin_tag, []);
  for (const s of filtered) {
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
          <span class="script-category-count">${scripts.length} 部</span>
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

function showScriptsLoading() {
  const list = $('#script-list');
  if (!list) return;
  list.innerHTML = `
    <div id="script-list-loading" class="echoes-cold-start">
      <p class="echoes-cold-start-text">正在唤醒沉睡的剧本…</p>
      <p class="echoes-cold-start-hint">若刚从休眠中醒来，可能需要稍等片刻</p>
    </div>
  `;
}

async function loadScripts() {
  showScriptsLoading();
  try {
    const res = await fetch('/api/scripts');
    if (res.status === 401) {
      showInviteGate(true);
      return;
    }
    if (!res.ok) throw new Error('load failed');
    const data = await res.json();
    state.allScripts = (data && data.scripts) || [];
    renderScriptList();
  } catch (err) {
    console.error(err);
    const list = $('#script-list');
    if (list) {
      list.innerHTML = `
        <div class="echoes-cold-start">
          <p class="echoes-cold-start-text">剧本还在沉睡中…</p>
          <p class="echoes-cold-start-hint">请稍后再试，或刷新页面</p>
        </div>
      `;
    }
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
    openSettings();
    return;
  }

  _briefingScriptId = scriptId;

  let detail;
  try {
    const res = await fetch(`/api/scripts/${scriptId}/detail`);
    if (res.status === 401) {
      showInviteGate(true);
      return;
    }
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

  $('#briefing-ai-name').textContent = detail.ai_character.name;
  $('#briefing-ai-intro').textContent = detail.ai_character.intro;

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
    openSettings();
    return;
  }

  hideEnding();
  const llmConfig = getEffectiveLLMConfig();
  const payload = { script_id: scriptId };
  if (llmConfig) payload.llm_config = llmConfig;
  if (aiName) payload.ai_name = aiName;
  if (aiPersona) payload.ai_persona = aiPersona;
  if (state.pendingSaveId) payload.save_id = state.pendingSaveId;

  try {
    const token = window._supabaseSession?.access_token;
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      showInviteGate(true);
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
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
    state.flowEntries = [];

    state.pendingSaveId = null;
    hideEnding();
    showScreen('game');
    window.dispatchEvent(new CustomEvent('echoes:session-started', {
      detail: { ...data, scriptDetail },
    }));
  } catch (err) {
    alert(err.message || '启动游戏失败，请重试');
    console.error(err);
  }
}

function sharePayload() {
  const ending = state.lastEnding || {};
  return {
    title: state.script?.chapter_title || state.script?.title || '',
    endingTitle: ending.endingTitle || '',
    endingText: ending.endingText || '',
    stats: state.stats,
    echoes: (state.flowEntries || []).filter((e) => e.type === 'echo'),
    entries: state.flowEntries || [],
    originTag: state.script?.origin_tag || '',
    aiName: state.aiName,
    playerName: state.playerName,
    perfId: state.perfId,
  };
}

function setShareStatus(text) {
  const el = $('#share-status');
  if (!el) return;
  if (!text) {
    el.setAttribute('hidden', '');
    el.textContent = '';
    return;
  }
  el.removeAttribute('hidden');
  el.textContent = text;
}

async function withShareBusy(btn, fn) {
  const buttons = $$('.echoes-share-btn');
  buttons.forEach((b) => { b.disabled = true; });
  try {
    await fn();
  } finally {
    buttons.forEach((b) => { b.disabled = false; });
  }
}

$('#share-essence-btn')?.addEventListener('click', () => {
  withShareBusy($('#share-essence-btn'), async () => {
    setShareStatus('正在生成精华卡片…');
    try {
      const payload = sharePayload();
      const result = await exportEssenceImage(payload);
      const mode = await shareOrDownload(result, buildShareCopy(payload));
      setShareStatus(mode === 'shared' ? '已调起系统分享' : '图片已下载（静态快照，不可续玩）');
    } catch (err) {
      console.error(err);
      setShareStatus(err.message || '生成失败，请重试');
    }
  });
});

$('#share-full-btn')?.addEventListener('click', () => {
  withShareBusy($('#share-full-btn'), async () => {
    setShareStatus('正在生成完整回顾（较长图片）…');
    try {
      const payload = sharePayload();
      const result = await exportFullImage(payload);
      const mode = await shareOrDownload(result, buildShareCopy(payload));
      setShareStatus(mode === 'shared' ? '已调起系统分享' : '完整回顾已下载');
    } catch (err) {
      console.error(err);
      setShareStatus(err.message || '生成失败，请重试');
    }
  });
});

$('#share-txt-btn')?.addEventListener('click', () => {
  exportTranscript(sharePayload());
  setShareStatus('纯文本记录已下载');
});

$('#share-copy-btn')?.addEventListener('click', async () => {
  const ok = await copyText(buildShareCopy(sharePayload()));
  setShareStatus(ok ? '分享文案已复制（含体验链接）' : '复制失败，请手动选择文案');
});

window.addEventListener('echoes:game-over', (e) => {
  const d = e.detail || {};
  state.gameOver = true;
  state.stats = d.stats || state.stats;
  state.turn = d.turn ?? state.turn;
  state.flowEntries = d.entries || [];
  showEnding(d.outcome, d.ending_text, d.turn, d.maxTurns, { entries: d.entries });
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

$('#settings-open-btn')?.addEventListener('click', openSettings);
$('#config-warning-link')?.addEventListener('click', openSettings);
$('#settings-close-btn')?.addEventListener('click', closeSettings);
$('#settings-overlay')?.addEventListener('click', (e) => {
  if (e.target === $('#settings-overlay')) closeSettings();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#settings-overlay')?.classList.contains('hidden')) {
    closeSettings();
  }
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
  setTimeout(() => closeSettings(), 450);
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

$('#invite-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const code = $('#invite-code-input')?.value.trim() || '';
  const errEl = $('#invite-gate-error');
  if (errEl) {
    errEl.classList.add('hidden');
    errEl.textContent = '';
  }
  try {
    const res = await fetch('/api/access/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || '邀请码不对');
    }
    location.reload();
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || '邀请码不对，再看看？';
      errEl.classList.remove('hidden');
    }
  }
});

async function ensureInvite() {
  try {
    const probe = await fetch('/api/scripts');
    if (probe.status === 401) {
      showInviteGate(true);
      return false;
    }
    return true;
  } catch (err) {
    console.error(err);
    return true; // network blip: don't block on invite
  }
}

// ── Auth ────────────────────────────────────────────────────────

let _supabase = null;

async function initSupabase() {
  try {
    const res = await fetch('/api/config/supabase');
    if (!res.ok) return;
    const { supabase_url, supabase_anon_key } = await res.json();
    if (!supabase_url || !supabase_anon_key) return;
    _supabase = window.supabase?.createClient(supabase_url, supabase_anon_key);
    if (!_supabase) return;

    _supabase.auth.onAuthStateChange((_event, session) => {
      window._supabaseSession = session;
      updateAuthButton(session?.user ?? null);
    });

    const { data: { session } } = await _supabase.auth.getSession();
    window._supabaseSession = session;
    updateAuthButton(session?.user ?? null);
  } catch (err) {
    console.warn('[auth] initSupabase failed:', err);
  }
}

function updateAuthButton(user) {
  const btn = $('#auth-btn');
  if (!btn) return;
  btn.classList.remove('hidden');
  if (user) {
    const email = user.email || '';
    btn.textContent = email ? `我的记录 (${email.split('@')[0]})` : '我的记录';
    btn.dataset.mode = 'history';
  } else {
    btn.textContent = '登录';
    btn.dataset.mode = 'login';
  }
}

function openAuthModal() {
  $('#auth-form-pane')?.classList.remove('hidden');
  $('#auth-sent-pane')?.classList.add('hidden');
  $('#auth-email-input').value = '';
  $('#auth-form-error')?.classList.add('hidden');
  $('#auth-modal')?.classList.remove('hidden');
}

function closeAuthModal() {
  $('#auth-modal')?.classList.add('hidden');
}

async function sendMagicLink(email) {
  if (!_supabase) throw new Error('账号功能暂未配置，请联系管理员设置 Supabase 环境变量');
  const { error } = await _supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: window.location.origin },
  });
  if (error) throw new Error(error.message);
}

async function openHistoryModal() {
  $('#history-modal')?.classList.remove('hidden');
  $('#history-loading')?.classList.remove('hidden');
  $('#history-list')?.classList.add('hidden');
  try {
    const token = window._supabaseSession?.access_token;
    const res = await fetch('/api/me/history', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('未登录');
    const data = await res.json();
    renderHistory(data);
  } catch (err) {
    const el = $('#history-loading');
    if (el) { el.textContent = err.message || '加载失败'; el.classList.remove('hidden'); }
  }
}

function renderHistory({ short_play_records = [], long_form_progress = [] }) {
  const list = $('#history-list');
  if (!list) return;
  list.innerHTML = '';

  if (!short_play_records.length && !long_form_progress.length) {
    list.innerHTML = '<p style="color:var(--echo-muted);font-size:0.8125rem">暂无游玩记录</p>';
  } else {
    if (short_play_records.length) {
      const h = document.createElement('p');
      h.className = 'echoes-briefing-section-label';
      h.textContent = '特写';
      list.appendChild(h);
      for (const r of short_play_records) {
        const row = document.createElement('div');
        row.className = 'history-row';
        const date = r.completed_at ? new Date(r.completed_at).toLocaleDateString('zh-CN') : '';
        row.innerHTML = `<span class="history-work">${r.work_id}</span><span class="history-meta">${r.outcome === 'win' ? '达成' : '失败'} · ${date}</span>`;
        list.appendChild(row);
      }
    }
    if (long_form_progress.length) {
      const h = document.createElement('p');
      h.className = 'echoes-briefing-section-label';
      h.style.marginTop = '0.75rem';
      h.textContent = '长镜';
      list.appendChild(h);
      for (const r of long_form_progress) {
        const row = document.createElement('div');
        row.className = 'history-row';
        const endings = (r.discovered_endings || []).length;
        row.innerHTML = `<span class="history-work">${r.work_id}</span><span class="history-meta">已发现结局 ${endings} 个</span>`;
        list.appendChild(row);
      }
    }
  }

  $('#history-loading')?.classList.add('hidden');
  list.classList.remove('hidden');
}

$('#auth-btn')?.addEventListener('click', () => {
  if ($('#auth-btn').dataset.mode === 'history') {
    openHistoryModal();
  } else {
    openAuthModal();
  }
});

$('#auth-modal-cancel')?.addEventListener('click', closeAuthModal);
$('#auth-sent-close')?.addEventListener('click', closeAuthModal);
$('#auth-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#auth-modal')) closeAuthModal();
});

$('#auth-email-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = $('#auth-email-input')?.value.trim();
  const errEl = $('#auth-form-error');
  if (errEl) { errEl.classList.add('hidden'); errEl.textContent = ''; }
  const btn = $('#auth-submit-btn');
  if (btn) btn.disabled = true;
  try {
    await sendMagicLink(email);
    $('#auth-form-pane')?.classList.add('hidden');
    $('#auth-sent-pane')?.classList.remove('hidden');
  } catch (err) {
    if (errEl) { errEl.textContent = err.message || '发送失败，请重试'; errEl.classList.remove('hidden'); }
  } finally {
    if (btn) btn.disabled = false;
  }
});

$('#history-modal-close')?.addEventListener('click', () => {
  $('#history-modal')?.classList.add('hidden');
});
$('#history-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#history-modal')) $('#history-modal').classList.add('hidden');
});

window.addEventListener('echoes:restart-work', async (e) => {
  const workId = e.detail?.work_id;
  if (!workId) return;
  state.pendingSaveId = null;
  await startGame(workId);
});

async function bootstrap() {
  try {
    fillSiteCredit();
    bindModeSwitch();
    fillLLMForm(loadStoredLLMConfig() || { provider: 'doubao', ...PROVIDER_DEFAULTS.doubao, api_key: '' });
    showScreen('select');

    const ok = await ensureInvite();
    if (!ok) return;

    state.authorized = true;
    showInviteGate(false);
    await Promise.all([refreshLLMStatus(), loadScripts(), initSupabase()]);
  } catch (err) {
    console.error('bootstrap failed', err);
    showScreen('select');
  }
}

bootstrap();
