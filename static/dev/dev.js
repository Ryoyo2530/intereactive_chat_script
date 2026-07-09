// ── Constants ─────────────────────────────────────────────────────────────────

const DEV_LLM_STORAGE_KEY = 'ruxi_dev_llm_config';
const DEV_DRAFT_PREFIX = 'ruxi_dev_draft_';

const PROVIDER_DEFAULTS = {
  doubao: { api_base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-2-0-lite-260428' },
  openai: { api_base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { api_base: '', model: '' },
};

const SCRIPT_TEMPLATE = {
  id: "new_script_001",
  title: "新剧本",
  origin_tag: "你也一定遇到过",
  theme_tags: ["恋爱"],
  teaser: "一句话简介，展示在剧本列表",
  briefing: "入场须知，告诉玩家背景和目标",
  objective: "玩家目标描述",
  player_role_hint: "扮演：你自己",
  estimated_turns_hint: "约 8-12 轮",
  background: "剧情背景，供LLM参考",
  ai_character: {
    name: "对手角色名",
    persona: "角色性格描述",
    intro: "角色简介，展示在入场须知页面",
    emotion_vocabulary: ["开心", "平静", "疑惑", "不满", "愤怒", "感动"],
  },
  player_character: {
    name: "玩家",
    persona: "玩家角色设定"
  },
  stats: {
    "好感度": { initial: 50, min: 0, max: 100, direction: "higher_is_better" },
    "愤怒值": { initial: 20, min: 0, max: 100, direction: "lower_is_better" }
  },
  key_points: [
    { id: 1, description: "关键点描述：玩家说了什么有效的话", hit_stat_changes: { "好感度": [5, 15] } },
    { id: 2, description: "另一个关键点", hit_stat_changes: { "好感度": [8, 20] } },
    { id: 3, description: "第三个关键点", hit_stat_changes: { "愤怒值": [-15, -5] } }
  ],
  pitfalls: [
    { id: "p1", description: "踩雷描述：玩家说了什么错误的话", hit_stat_changes: { "愤怒值": [10, 25] } }
  ],
  win_condition: "好感度 >= 70 且 愤怒值 <= 30",
  lose_condition: "愤怒值 >= 80",
  max_turns: 12,
  opening_line: "角色的开场白……",
  ending_titles: { win: "成功", lose: "失败" }
};

// ── State ─────────────────────────────────────────────────────────────────────

const CATEGORY_META = [
  { origin_tag: '影视同人', display: '影视热梗', subtitle: '这一世由你夺回一切' },
  { origin_tag: '你也一定遇到过', display: '你也一定遇到过', subtitle: '如何炼就一张好嘴' },
];

const state = {
  scripts: {},
  activeId: null,
  dirtyIds: new Set(),
  isNewDraft: false,
  simSessionId: null,
  simScriptId: null,
  simAiName: null,
  simStatsConfig: null,
  pendingImportFile: null,
  activeTab: 'editor',
  workspace: 'scripts',
  scriptTab: 'editor',
  llmTab: 'prompts',
  pathSelectedKp: new Set(),
  pathSelectedPf: new Set(),
  debugLog: [],
  statTimeline: [],
  simLlmConfig: null,
  promptProduction: {},
  promptBuffer: {},
  activePromptKey: 'director/system.txt',
  promptServerDraftSaved: false,
  scriptServerDraftSaved: false,
  showScriptDiff: false,
  showPromptDiff: false,
};

const PROMPT_KEYS = [
  { key: 'director/system.txt', label: '导演 · system', agent: '导演' },
  { key: 'director/user.txt', label: '导演 · user', agent: '导演' },
  { key: 'roleplay/system.txt', label: '演员 · system', agent: '演员' },
  { key: 'roleplay/user.txt', label: '演员 · user', agent: '演员' },
  { key: 'hint/system.txt', label: '提示 · system', agent: '提示' },
  { key: 'hint/user.txt', label: '提示 · user', agent: '提示' },
];

const $ = (sel) => document.querySelector(sel);

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function computeLineDiff(oldText, newText) {
  const a = (oldText ?? '').split('\n');
  const b = (newText ?? '').split('\n');
  const m = a.length;
  const n = b.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const out = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      out.unshift({ type: 'same', line: a[i - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      out.unshift({ type: 'add', line: b[j - 1] });
      j -= 1;
    } else {
      out.unshift({ type: 'del', line: a[i - 1] });
      i -= 1;
    }
  }
  return out;
}

function renderDiffPanel(container, oldText, newText, emptyMessage) {
  const panel = typeof container === 'string' ? $(container) : container;
  if (oldText === newText) {
    panel.innerHTML = `<div class="diff-empty">${escHtml(emptyMessage || '草稿与生产版一致，无差异')}</div>`;
    return;
  }
  const diff = computeLineDiff(oldText, newText);
  panel.innerHTML = diff.map((row) => {
    const prefix = row.type === 'add' ? '+ ' : row.type === 'del' ? '- ' : '  ';
    return `<div class="diff-line diff-${row.type}">${escHtml(prefix + row.line)}</div>`;
  }).join('');
}

function updateScriptDraftStatus() {
  const el = $('#script-draft-status');
  if (!el) return;
  if (state.scriptServerDraftSaved) {
    el.textContent = '草稿已保存到缓冲区（试玩将使用此版本）';
    el.className = 'draft-status saved';
  } else if (state.activeId && state.dirtyIds.has(state.activeId)) {
    el.textContent = '有未保存修改 · 点击 Save Draft 使草稿生效';
    el.className = 'draft-status unsaved';
  } else {
    el.textContent = '草稿未保存到缓冲区';
    el.className = 'draft-status';
  }
}

function updatePromptDraftStatus() {
  const el = $('#prompt-draft-status');
  if (!el) return;
  if (state.promptServerDraftSaved) {
    el.textContent = 'Prompt 草稿已保存（试玩将使用此版本）';
    el.className = 'draft-status saved';
  } else if (promptBufferDiffersFromProduction()) {
    el.textContent = '有未保存修改 · 点击 Save Draft 使草稿生效';
    el.className = 'draft-status unsaved';
  } else {
    el.textContent = '草稿未保存到缓冲区';
    el.className = 'draft-status';
  }
}

function promptBufferDiffersFromProduction() {
  return PROMPT_KEYS.some(({ key }) => (state.promptBuffer[key] ?? '') !== (state.promptProduction[key] ?? ''));
}

function syncPromptBufferFromEditor() {
  const key = state.activePromptKey;
  if (key && $('#prompt-textarea')) {
    state.promptBuffer[key] = $('#prompt-textarea').value;
  }
}

function getPromptBufferSnapshot() {
  syncPromptBufferFromEditor();
  const out = {};
  for (const { key } of PROMPT_KEYS) {
    out[key] = state.promptBuffer[key] ?? state.promptProduction[key] ?? '';
  }
  return out;
}

function getProductionScriptText(id) {
  const script = state.scripts[id];
  return script ? JSON.stringify(script, null, 2) : '';
}

function getDraftScriptText() {
  return $('#json-editor').value;
}

function formatDebugAgent(obj) {
  if (!obj) return '(无数据)';
  const output = obj.output ?? obj;
  if (typeof output !== 'object' || output === null) return String(output);
  return Object.entries(output).map(([k, v]) => {
    const val = (typeof v === 'object' && v !== null) ? JSON.stringify(v) : String(v);
    return `${k}: ${val}`;
  }).join('\n');
}

function formatTokenUsage(usage) {
  if (!usage) return '输入 — · 输出 —';
  const inp = usage.input_tokens ?? '—';
  const out = usage.output_tokens ?? '—';
  return `输入 ${inp} · 输出 ${out}`;
}

function formatLlmConfigSummary(llmCfg) {
  if (!llmCfg) return '';
  const d = llmCfg.director?.model || '—';
  const r = llmCfg.roleplay?.model || d;
  return d === r ? `模型 · ${d}` : `导演 · ${d} / 演员 · ${r}`;
}

function buildAgentDebugHtml(label, agent) {
  if (!agent) {
    return `<div class="debug-agent"><p class="debug-agent-title">${escHtml(label)}</p><pre>(无数据)</pre></div>`;
  }
  const outputText = formatDebugAgent(agent);
  const timing = agent.ttft_ms != null
    ? `<div class="debug-meta">模型: ${escHtml(agent.model || '—')} · 首token: ${agent.ttft_ms}ms · 总耗时: ${agent.total_ms}ms · Token: ${formatTokenUsage(agent.usage)}</div>`
    : (agent.model ? `<div class="debug-meta">模型: ${escHtml(agent.model)}</div>` : '');
  const prompts = agent.prompts || {};
  const promptHtml = (prompts.system || prompts.user) ? `
    <button type="button" class="debug-prompt-toggle" data-expanded="false">原始 Prompt ▶</button>
    <div class="debug-prompt-content hidden">
      <div class="debug-prompt-block">
        <div class="debug-prompt-label">system</div>
        <pre>${escHtml(prompts.system || '')}</pre>
      </div>
      <div class="debug-prompt-block">
        <div class="debug-prompt-label">user</div>
        <pre>${escHtml(prompts.user || '')}</pre>
      </div>
    </div>
  ` : '';

  return `
    <div class="debug-agent">
      <p class="debug-agent-title">${escHtml(label)}</p>
      ${promptHtml}
      <pre>${escHtml(outputText)}</pre>
      ${timing}
    </div>
  `;
}

// ── Dev LLM config ────────────────────────────────────────────────────────────

function loadDevLLMConfig() {
  try {
    return JSON.parse(localStorage.getItem(DEV_LLM_STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveDevLLMConfig(cfg) {
  localStorage.setItem(DEV_LLM_STORAGE_KEY, JSON.stringify(cfg));
}

function readDevLLMForm() {
  const same = $('#dev-llm-same-model').checked;
  const directorModel = $('#dev-llm-director-model').value.trim();
  return {
    provider: $('#dev-llm-provider').value,
    api_base: $('#dev-llm-api-base').value.trim(),
    api_key: $('#dev-llm-api-key').value.trim(),
    director_model: directorModel,
    roleplay_model: same ? directorModel : $('#dev-llm-roleplay-model').value.trim(),
    same_model: same,
  };
}

function fillDevLLMForm(cfg) {
  if (!cfg) return;
  $('#dev-llm-provider').value = cfg.provider || 'doubao';
  $('#dev-llm-api-base').value = cfg.api_base || '';
  $('#dev-llm-api-key').value = cfg.api_key || '';
  $('#dev-llm-director-model').value = cfg.director_model || cfg.model || '';
  $('#dev-llm-roleplay-model').value = cfg.roleplay_model || cfg.model || '';
  $('#dev-llm-same-model').checked = cfg.same_model !== false;
  syncDevLLMSameModel();
}

function syncDevLLMSameModel() {
  const same = $('#dev-llm-same-model').checked;
  const rpField = $('#dev-llm-roleplay-model');
  rpField.disabled = same;
  if (same) rpField.value = $('#dev-llm-director-model').value;
}

function updateDevLLMSummary() {
  const cfg = readDevLLMForm();
  const d = cfg.director_model || '未设置';
  const r = cfg.same_model ? d : (cfg.roleplay_model || '未设置');
  $('#dev-llm-summary').textContent = cfg.same_model
    ? `导演/演员 · ${d}`
    : `导演 · ${d} / 演员 · ${r}`;
}

function getDevLLMPayload() {
  const cfg = readDevLLMForm();
  if (!cfg.api_base || !cfg.director_model) return null;
  return {
    provider: cfg.provider,
    api_base: cfg.api_base,
    api_key: cfg.api_key,
    director_model: cfg.director_model,
    roleplay_model: cfg.roleplay_model || cfg.director_model,
  };
}

async function initDevLLMConfig() {
  let cfg = loadDevLLMConfig();
  if (!cfg) {
    try {
      const res = await fetch('/api/config/llm');
      const data = await res.json();
      if (data.configured) {
        cfg = {
          provider: data.provider || 'doubao',
          api_base: data.api_base || '',
          api_key: '',
          director_model: data.model || '',
          roleplay_model: data.model || '',
          same_model: true,
        };
      }
    } catch { /* ignore */ }
  }
  if (!cfg) {
    cfg = {
      provider: 'doubao',
      api_base: PROVIDER_DEFAULTS.doubao.api_base,
      api_key: '',
      director_model: PROVIDER_DEFAULTS.doubao.model,
      roleplay_model: PROVIDER_DEFAULTS.doubao.model,
      same_model: true,
    };
  }
  fillDevLLMForm(cfg);
  updateDevLLMSummary();
}

$('#dev-llm-toggle').addEventListener('click', () => {
  const panel = $('#dev-llm-panel');
  const chevron = $('#dev-llm-chevron');
  const hidden = panel.classList.toggle('hidden');
  chevron.textContent = hidden ? '▶' : '▼';
});

$('#dev-llm-provider').addEventListener('change', () => {
  const p = $('#dev-llm-provider').value;
  const d = PROVIDER_DEFAULTS[p] || PROVIDER_DEFAULTS.custom;
  if (p !== 'custom') $('#dev-llm-api-base').value = d.api_base;
  if (!$('#dev-llm-director-model').value || Object.values(PROVIDER_DEFAULTS).some((x) => x.model === $('#dev-llm-director-model').value)) {
    $('#dev-llm-director-model').value = d.model;
  }
  syncDevLLMSameModel();
  updateDevLLMSummary();
});

$('#dev-llm-same-model').addEventListener('change', syncDevLLMSameModel);
$('#dev-llm-director-model').addEventListener('input', () => {
  if ($('#dev-llm-same-model').checked) syncDevLLMSameModel();
  updateDevLLMSummary();
});
$('#dev-llm-roleplay-model').addEventListener('input', updateDevLLMSummary);

$('#dev-llm-save-btn').addEventListener('click', () => {
  const cfg = readDevLLMForm();
  saveDevLLMConfig(cfg);
  updateDevLLMSummary();
  $('#dev-llm-status').textContent = '已保存';
});

$('#dev-llm-test-btn').addEventListener('click', async () => {
  const cfg = readDevLLMForm();
  if (!cfg.api_base || !cfg.api_key || !cfg.director_model) {
    $('#dev-llm-status').textContent = '请填写 API Base、Key 和导演 Model';
    return;
  }
  $('#dev-llm-status').textContent = '测试中…';
  try {
    const res = await fetch('/api/config/llm/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: cfg.provider,
        api_base: cfg.api_base,
        api_key: cfg.api_key,
        model: cfg.director_model,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '失败');
    saveDevLLMConfig(cfg);
    $('#dev-llm-status').textContent = `连接成功 · ${data.preview || data.model}`;
  } catch (err) {
    $('#dev-llm-status').textContent = `失败: ${err.message}`;
  }
});

// ── Stat timeline board ───────────────────────────────────────────────────────

function statSeverity(value, cfg) {
  const min = cfg.min ?? 0;
  const max = cfg.max ?? 100;
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const good = cfg.direction === 'lower_is_better' ? 1 - pct : pct;
  if (good > 0.6) return '#4ade80';
  if (good > 0.3) return '#f59e0b';
  return '#ef4444';
}

function pushStatTimeline(turn, stats, statChanges = {}) {
  state.statTimeline.push({
    turn,
    stats: { ...stats },
    stat_changes: { ...statChanges },
  });
  renderStatTimeline();
}

function renderStatTimeline() {
  const container = $('#sim-stat-timeline');
  const cfg = state.simStatsConfig || {};
  const timeline = state.statTimeline;

  if (!timeline.length) {
    container.innerHTML = '<div class="timeline-empty">开始测试对局后，这里会展示各轮数值变化轨迹与难度节奏。</div>';
    return;
  }

  const statNames = Object.keys(timeline[timeline.length - 1].stats);
  container.innerHTML = '';

  for (const name of statNames) {
    const statCfg = cfg[name] || { min: 0, max: 100, direction: 'lower_is_better' };
    const min = statCfg.min ?? 0;
    const max = statCfg.max ?? 100;
    const latest = timeline[timeline.length - 1].stats[name];

    const block = document.createElement('div');
    block.className = 'timeline-stat-block';

    const track = document.createElement('div');
    track.className = 'timeline-track';
    const fill = document.createElement('div');
    fill.className = 'timeline-fill';
    const latestPct = Math.max(0, Math.min(100, ((latest - min) / (max - min || 1)) * 100));
    fill.style.width = `${latestPct}%`;
    fill.style.background = statSeverity(latest, statCfg);
    track.appendChild(fill);

    timeline.forEach((entry) => {
      const val = entry.stats[name];
      const pct = Math.max(0, Math.min(100, ((val - min) / (max - min || 1)) * 100));
      const dot = document.createElement('div');
      dot.className = 'timeline-point';
      dot.style.left = `${pct}%`;
      dot.style.background = statSeverity(val, statCfg);
      dot.title = `第 ${entry.turn} 轮: ${val}`;
      track.appendChild(dot);
    });

    const steps = document.createElement('div');
    steps.className = 'timeline-steps';
    timeline.forEach((entry, idx) => {
      if (idx === 0) return;
      const delta = entry.stat_changes?.[name];
      if (delta == null || delta === 0) return;
      const chip = document.createElement('span');
      const positive = statCfg.direction === 'lower_is_better' ? delta < 0 : delta > 0;
      chip.className = `timeline-step ${delta === 0 ? 'neutral' : positive ? 'positive' : 'negative'}`;
      chip.textContent = `T${entry.turn} ${delta > 0 ? '+' : ''}${delta}`;
      steps.appendChild(chip);
    });

    block.innerHTML = `<div class="timeline-stat-name"><span>${escHtml(name)}</span><span>${latest}</span></div>`;
    block.appendChild(track);

    const labels = document.createElement('div');
    labels.className = 'timeline-turn-labels';
    labels.innerHTML = `<span>min ${min}</span><span>max ${max}</span>`;
    block.appendChild(labels);
    block.appendChild(steps);
    container.appendChild(block);
  }
}

function resetStatTimeline(initialStats) {
  state.statTimeline = [{ turn: 0, stats: { ...initialStats }, stat_changes: {} }];
  renderStatTimeline();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

async function doLogin() {
  const pw = $('#login-pw').value;
  if (!pw) return;
  try {
    const res = await fetch('/api/dev/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
    });
    if (!res.ok) {
      const err = await res.json();
      $('#login-error').textContent = err.detail || '密码错误';
      $('#login-error').classList.remove('hidden');
      return;
    }
    await loadScripts();
    showApp();
    await initDevLLMConfig();
  } catch {
    $('#login-error').textContent = '网络错误';
    $('#login-error').classList.remove('hidden');
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  const res = await fetch('/api/dev/scripts', { credentials: 'same-origin' });
  if (res.status === 401) {
    showLogin();
    return;
  }
  const data = await res.json();
  state.scripts = {};
  for (const s of (data.scripts || [])) state.scripts[s.id] = s;
  showApp();
  renderScriptList();
  updateDetailHeader();
  await initDevLLMConfig();
  await ensurePromptsLoaded();
}

function showLogin() {
  $('#login-screen').classList.remove('hidden');
  $('#app-screen').classList.remove('visible');
  $('#app-screen').classList.add('hidden');
}

function showApp() {
  $('#login-screen').classList.add('hidden');
  $('#app-screen').classList.remove('hidden');
  $('#app-screen').classList.add('visible');
}

// ── Script list ───────────────────────────────────────────────────────────────

async function loadScripts() {
  const res = await fetch('/api/dev/scripts', { credentials: 'same-origin' });
  if (res.status === 401) { showLogin(); return; }
  if (!res.ok) return;
  const data = await res.json();
  state.scripts = {};
  for (const s of (data.scripts || [])) state.scripts[s.id] = s;
  renderScriptList();
  fillScriptSelects();
}

function fillScriptSelects(preferredId) {
  const sel = $('#prompt-script-select');
  if (!sel) return;
  const preferred = preferredId || state.activeId || '';
  const current = preferred || sel.value || '';
  sel.innerHTML = '<option value="">— 选择剧本 —</option>';
  for (const s of Object.values(state.scripts)) {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.title || s.id;
    sel.appendChild(opt);
  }
  if (current && state.scripts[current]) sel.value = current;
}

function switchWorkspace(workspace) {
  state.workspace = workspace;
  document.querySelectorAll('.workspace-nav-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.workspace === workspace);
  });
  document.querySelectorAll('.workspace').forEach((el) => {
    el.classList.toggle('active', el.id === `workspace-${workspace}`);
  });
  if (workspace === 'llm') {
    ensurePromptsLoaded();
    fillScriptSelects();
  } else {
    switchTab(state.scriptTab || 'editor');
  }
}

function switchTab(tab) {
  if (state.workspace === 'scripts') {
    state.scriptTab = tab;
    state.activeTab = tab;
  } else {
    state.llmTab = tab;
    state.activeTab = tab;
  }

  const ws = state.workspace;
  document.querySelectorAll(`.tab-btn[data-workspace="${ws}"]`).forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });

  if (ws === 'scripts') {
    document.querySelectorAll('.script-tab').forEach((panel) => {
      panel.classList.toggle('active', panel.id === `tab-${tab}`);
    });
    if (tab === 'path') renderPathCalculator();
    if (tab === 'simulate') updateSimControls();
    return;
  }

  document.querySelectorAll('.llm-tab').forEach((panel) => {
    panel.classList.toggle('active', panel.id === 'tab-prompts');
  });
  ensurePromptsLoaded();
}

function updateSimControls() {
  const simLabel = $('#sim-label');
  const simStartBtn = $('#sim-start-btn');
  if (!simLabel || !simStartBtn) return;

  const promptHint = state.promptServerDraftSaved || promptBufferDiffersFromProduction() ? ' · Prompt 草稿' : '';

  if (state.isNewDraft) {
    const draft = parseEditorJson();
    const draftId = draft?.id;
    simLabel.textContent = draftId
      ? `试玩 · ${draft.title || draftId}（未保存草稿）${promptHint}`
      : '请先填写剧本 id';
    simStartBtn.disabled = !draftId;
    return;
  }

  const id = state.activeId;
  if (!id) {
    simLabel.textContent = '请先选择剧本';
    simStartBtn.disabled = true;
    return;
  }

  const script = state.scripts[id];
  const draftHint = state.scriptServerDraftSaved || state.dirtyIds.has(id) ? '（草稿）' : '';
  simLabel.textContent = `试玩 · ${script?.title || id}${draftHint}${promptHint}`;
  simStartBtn.disabled = false;
}

async function resolveSimScriptPayload(scriptId) {
  if (!scriptId) return null;
  try {
    const draftRes = await fetch(`/api/dev/drafts/scripts/${scriptId}`, { credentials: 'same-origin' });
    if (draftRes.ok) {
      const data = await draftRes.json();
      if (data.has_draft && data.draft) return data.draft;
    }
  } catch { /* ignore */ }
  if (state.activeId === scriptId) {
    const editorScript = parseEditorJson();
    if (editorScript?.id === scriptId) return editorScript;
  }
  return state.scripts[scriptId] || null;
}

function updateDetailHeader() {
  const titleEl = $('#topbar-title');
  const idEl = $('#topbar-id');

  if (state.isNewDraft) {
    const draft = parseEditorJson();
    const draftId = draft?.id;
    titleEl.textContent = draft?.title ? `${draft.title}（草稿）` : '新剧本（草稿）';
    idEl.textContent = draftId || '未保存';
    updateScriptDraftStatus();
    $('#save-btn').disabled = false;
    $('#download-btn').disabled = !draftId;
    $('#delete-btn').disabled = true;
    updateSimControls();
    return;
  }

  const script = state.activeId ? state.scripts[state.activeId] : null;
  if (!script) {
    titleEl.textContent = '请选择剧本';
    idEl.textContent = '';
    $('#save-btn').disabled = true;
    $('#download-btn').disabled = true;
    $('#delete-btn').disabled = true;
    updateScriptDraftStatus();
    updateSimControls();
    return;
  }

  const draftSuffix = state.dirtyIds.has(script.id) ? ' · 未保存' : '';
  titleEl.textContent = (script.title || script.id) + draftSuffix;
  idEl.textContent = script.id;
  updateScriptDraftStatus();
  $('#save-btn').disabled = false;
  $('#download-btn').disabled = false;
  $('#delete-btn').disabled = false;
  fillScriptSelects(script.id);
  updateSimControls();
}

function renderScriptList() {
  const container = $('#script-items');
  container.innerHTML = '';
  const scripts = Object.values(state.scripts);

  if (scripts.length === 0) {
    container.innerHTML = '<div style="padding:16px 12px;font-size:12px;color:var(--text-muted)">暂无剧本</div>';
    return;
  }

  const grouped = new Map();
  for (const meta of CATEGORY_META) grouped.set(meta.origin_tag, []);
  for (const s of scripts) {
    const tag = s.origin_tag || '未分类';
    if (!grouped.has(tag)) grouped.set(tag, []);
    grouped.get(tag).push(s);
  }

  for (const [originTag, items] of grouped) {
    if (!items.length) continue;
    const meta = CATEGORY_META.find((m) => m.origin_tag === originTag);
    const section = document.createElement('div');
    section.className = 'script-category';

    const header = document.createElement('div');
    header.className = 'script-category-header';
    header.innerHTML = `
      <div class="script-category-heading">
        <div class="script-category-name">${escHtml(meta?.display || originTag)}</div>
        ${meta?.subtitle ? `<div class="script-category-subtitle">${escHtml(meta.subtitle)}</div>` : ''}
      </div>
      <span class="script-category-count">${items.length}</span>
    `;
    section.appendChild(header);

    const list = document.createElement('div');
    list.className = 'script-category-items';

    for (const s of items) {
      const isActive = s.id === state.activeId;
      const isDraft = state.dirtyIds.has(s.id);
      const item = document.createElement('div');
      item.className = 'script-item' + (isActive ? ' active' : '');
      item.dataset.id = s.id;
      item.innerHTML = `
        <div class="status-dot ${isDraft ? 'draft' : 'saved'}"></div>
        <div class="script-item-body">
          <div class="script-item-title">${escHtml(s.title || s.id)}</div>
          <div class="script-item-id">${escHtml(s.id)}</div>
        </div>
      `;
      item.addEventListener('click', () => selectScript(s.id));
      list.appendChild(item);
    }

    section.appendChild(list);
    container.appendChild(section);
  }
}

function selectScript(id) {
  state.activeId = id;
  state.isNewDraft = false;
  state.pathSelectedKp = new Set();
  state.pathSelectedPf = new Set();
  const script = state.scripts[id];
  const draft = loadEditorDraft(id);
  if (draft?.text) {
    $('#json-editor').value = draft.text;
    state.dirtyIds.add(id);
  } else if (script) {
    $('#json-editor').value = JSON.stringify(script, null, 2);
  }
  renderScriptList();
  updateDetailHeader();
  renderPathCalculator();
  refreshScriptDraftStatus(id);
}

async function refreshScriptDraftStatus(id) {
  if (!id) {
    state.scriptServerDraftSaved = false;
    updateScriptDraftStatus();
    return;
  }
  try {
    const res = await fetch(`/api/dev/drafts/scripts/${id}`, { credentials: 'same-origin' });
    if (res.ok) {
      const data = await res.json();
      state.scriptServerDraftSaved = Boolean(data.has_draft);
    } else {
      state.scriptServerDraftSaved = false;
    }
  } catch {
    state.scriptServerDraftSaved = false;
  }
  updateScriptDraftStatus();
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.dataset.workspace !== state.workspace) return;
    switchTab(btn.dataset.tab);
  });
});

document.querySelectorAll('.workspace-nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => switchWorkspace(btn.dataset.workspace));
});

// ── Validation ────────────────────────────────────────────────────────────────

function clearValidation() {
  const bar = $('#validation-bar');
  bar.classList.remove('visible');
  bar.innerHTML = '';
}

function showValidation(result) {
  const container = $('#validation-bar');
  container.innerHTML = '';
  const { errors, warnings } = result;
  if (errors.length === 0 && warnings.length === 0) {
    container.innerHTML = '<span class="val-ok">✓ 校验通过，无问题</span>';
  }
  for (const e of errors) {
    const d = document.createElement('span');
    d.className = 'val-item val-error';
    d.textContent = '✕ ' + e;
    container.appendChild(d);
  }
  for (const w of warnings) {
    const d = document.createElement('span');
    d.className = 'val-item val-warning';
    d.textContent = '⚠ ' + w;
    container.appendChild(d);
  }
  container.classList.add('visible');
  return errors.length === 0;
}

function parseEditorJson() {
  try {
    return JSON.parse($('#json-editor').value);
  } catch {
    return null;
  }
}

function draftStorageKey(id) {
  return `${DEV_DRAFT_PREFIX}${id}`;
}

function saveEditorDraft(id, text) {
  if (!id) return;
  localStorage.setItem(draftStorageKey(id), JSON.stringify({
    text,
    updatedAt: Date.now(),
  }));
  state.dirtyIds.add(id);
}

function loadEditorDraft(id) {
  if (!id) return null;
  try {
    const raw = localStorage.getItem(draftStorageKey(id));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearEditorDraft(id) {
  if (!id) return;
  localStorage.removeItem(draftStorageKey(id));
}

function getActiveEditorScript() {
  return parseEditorJson();
}

function resolveSimScriptId() {
  const script = getActiveEditorScript();
  return script?.id || state.activeId || null;
}

function markEditorDirty() {
  const script = parseEditorJson();
  const id = script?.id || state.activeId;
  if (!id) return;
  saveEditorDraft(id, $('#json-editor').value);
  if (state.activeId && state.activeId !== id) {
    state.dirtyIds.add(state.activeId);
  }
  state.dirtyIds.add(id);
  state.scriptServerDraftSaved = false;
  updateDetailHeader();
  updateScriptDraftStatus();
  updateSimControls();
  if (state.activeTab === 'path') renderPathCalculator();
}

function parseApiErrors(errBody) {
  const detail = errBody?.detail;
  if (!detail) return ['保存失败'];
  if (typeof detail === 'string') return [detail];
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === 'string') return item;
      if (item?.msg) return item.msg;
      return JSON.stringify(item);
    });
  }
  if (detail.errors?.length) return detail.errors;
  return [JSON.stringify(detail)];
}

$('#script-draft-btn').addEventListener('click', async () => {
  const script = parseEditorJson();
  if (!script) {
    showValidation({ errors: ['JSON 格式错误，无法解析'], warnings: [] });
    return;
  }
  if (!script.id) {
    showValidation({ errors: ['Script 必须有 id 字段'], warnings: [] });
    return;
  }
  const res = await fetch(`/api/dev/drafts/scripts/${script.id}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(script),
  });
  if (!res.ok) {
    const err = await res.json();
    alert('保存草稿失败：' + (err.detail || res.statusText));
    return;
  }
  saveEditorDraft(script.id, $('#json-editor').value);
  state.scriptServerDraftSaved = true;
  state.dirtyIds.add(script.id);
  updateScriptDraftStatus();
  updateDetailHeader();
  $('#script-draft-status').textContent = '草稿已保存到缓冲区（试玩将使用此版本）';
});

$('#script-diff-btn').addEventListener('click', () => {
  const panel = $('#script-diff-panel');
  state.showScriptDiff = !state.showScriptDiff;
  panel.classList.toggle('hidden', !state.showScriptDiff);
  if (!state.showScriptDiff) return;
  const id = parseEditorJson()?.id || state.activeId;
  if (!id) {
    renderDiffPanel(panel, '', '', '请先选择或创建剧本');
    return;
  }
  renderDiffPanel(panel, getProductionScriptText(id), getDraftScriptText(), '草稿与生产版一致，无差异');
});

$('#save-btn').addEventListener('click', async () => {
  const script = parseEditorJson();
  if (!script) {
    showValidation({ errors: ['JSON 格式错误，无法解析'], warnings: [] });
    return;
  }
  const id = script.id;
  if (!id) {
    showValidation({ errors: ['Script 必须有 id 字段'], warnings: [] });
    return;
  }
  const method = state.scripts[id] ? 'PUT' : 'POST';
  const url = method === 'PUT' ? `/api/dev/scripts/${id}` : '/api/dev/scripts';
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(script),
  });
  if (!res.ok) {
    const err = await res.json();
    showValidation({
      errors: parseApiErrors(err),
      warnings: err.detail?.warnings || [],
    });
    return;
  }
  const data = await res.json();
  state.dirtyIds.delete(id);
  state.isNewDraft = false;
  state.scriptServerDraftSaved = false;
  clearEditorDraft(id);
  showValidation({ errors: [], warnings: data.warnings || [] });
  await loadScripts();
  fillScriptSelects(id);
  selectScript(id);
});

// ── Delete ────────────────────────────────────────────────────────────────────

$('#delete-btn').addEventListener('click', async () => {
  if (!state.activeId) return;
  const script = state.scripts[state.activeId];
  if (!confirm(`确定删除剧本「${script?.title || state.activeId}」？此操作不可撤销。`)) return;
  const res = await fetch(`/api/dev/scripts/${state.activeId}`, { method: 'DELETE', credentials: 'same-origin' });
  if (!res.ok) { alert('删除失败'); return; }
  clearEditorDraft(state.activeId);
  state.dirtyIds.delete(state.activeId);
  state.activeId = null;
  state.isNewDraft = false;
  $('#json-editor').value = '';
  clearValidation();
  await loadScripts();
  updateDetailHeader();
});

// ── Download single ───────────────────────────────────────────────────────────

$('#download-btn').addEventListener('click', () => {
  if (!state.activeId) return;
  const script = parseEditorJson() || state.scripts[state.activeId];
  if (!script) return;
  const blob = new Blob([JSON.stringify(script, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${state.activeId}.json`;
  a.click();
});

// ── Export all ────────────────────────────────────────────────────────────────

async function exportAllScripts() {
  const res = await fetch('/api/dev/export', { credentials: 'same-origin' });
  if (!res.ok) { alert('导出失败'); return; }
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'scripts.zip';
  a.click();
}

$('#export-all-btn').addEventListener('click', exportAllScripts);
$('#export-all-btn-2').addEventListener('click', exportAllScripts);

// ── New script ────────────────────────────────────────────────────────────────

$('#new-script-btn').addEventListener('click', () => {
  state.activeId = null;
  state.isNewDraft = true;
  renderScriptList();
  $('#json-editor').value = JSON.stringify(SCRIPT_TEMPLATE, null, 2);
  clearValidation();
  updateDetailHeader();
  switchTab('editor');
  renderPathCalculator();
  fillScriptSelects();
});

// ── Import ────────────────────────────────────────────────────────────────────

async function handleImportFile(file) {
  if (!file) return;
  state.pendingImportFile = file;

  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/dev/scripts/import', { method: 'POST', credentials: 'same-origin', body: fd });

  if (res.status === 422) {
    const err = await res.json();
    alert('校验失败：\n' + (err.detail?.errors || [err.detail]).join('\n'));
    return;
  }
  if (!res.ok) {
    const err = await res.json();
    alert('导入失败：' + (err.detail || '未知错误'));
    return;
  }
  const data = await res.json();
  if (data.conflict) {
    $('#conflict-id').textContent = data.existing_id;
    $('#import-modal').classList.add('visible');
    return;
  }
  await loadScripts();
  selectScript(data.id);
}

$('#import-file').addEventListener('change', (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  handleImportFile(file);
});
$('#import-file-2').addEventListener('change', (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  handleImportFile(file);
});

$('#conflict-overwrite').addEventListener('click', async () => {
  $('#import-modal').classList.remove('visible');
  if (!state.pendingImportFile) return;
  const fd = new FormData();
  fd.append('file', state.pendingImportFile);
  const res = await fetch('/api/dev/scripts/import/overwrite', { method: 'POST', credentials: 'same-origin', body: fd });
  state.pendingImportFile = null;
  if (!res.ok) { alert('覆盖失败'); return; }
  const data = await res.json();
  await loadScripts();
  selectScript(data.id);
});

$('#conflict-cancel').addEventListener('click', () => {
  $('#import-modal').classList.remove('visible');
  state.pendingImportFile = null;
});

// ── Simulate ──────────────────────────────────────────────────────────────────

function simAddMessage(role, text, opts = {}) {
  const { emotionTag = '', turn = null, debugData = null, debugOnly = false } = opts;
  const container = $('#sim-messages');
  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex;flex-direction:column;gap:6px;';

  if (role === 'user') {
    const bubble = document.createElement('div');
    bubble.className = 'bubble-user';
    bubble.innerHTML = `<div class="bubble-body">${escHtml(text)}</div>`;
    wrapper.appendChild(bubble);
  } else if (role === 'ai') {
    if (!debugOnly) {
      const bubble = document.createElement('div');
      bubble.className = 'bubble-ai';
      const name = state.simAiName || 'AI';
      const badgeHtml = emotionTag
        ? ` · <span class="emotion-badge">${escHtml(emotionTag)}</span>`
        : '';
      bubble.innerHTML = `
        <p class="bubble-meta">${escHtml(name)}${badgeHtml}</p>
        <div class="bubble-body">${escHtml(text)}</div>
      `;
      wrapper.appendChild(bubble);
    }

    if (debugData) {
      const turnLabel = turn != null ? ` · 第 ${turn} 轮` : '';
      const llmSummary = formatLlmConfigSummary(debugData.llm_config);
      const block = document.createElement('div');
      block.className = 'debug-block';
      block.innerHTML = `
        <button type="button" class="debug-toggle">
          <span>调试信息${escHtml(turnLabel)}</span>
          <span class="debug-chevron">▼</span>
        </button>
        <div class="debug-content">
          ${llmSummary ? `<div class="debug-meta" style="margin-bottom:6px">${escHtml(llmSummary)}</div>` : ''}
          ${buildAgentDebugHtml('导演 Agent', debugData.director)}
          ${buildAgentDebugHtml('演员 Agent', debugData.roleplay)}
        </div>
      `;
      block.querySelectorAll('.debug-prompt-toggle').forEach((btn) => {
        btn.addEventListener('click', () => {
          const content = btn.nextElementSibling;
          const expanded = btn.dataset.expanded === 'true';
          btn.dataset.expanded = expanded ? 'false' : 'true';
          btn.textContent = expanded ? '原始 Prompt ▶' : '原始 Prompt ▼';
          content.classList.toggle('hidden', expanded);
        });
      });
      block.querySelector('.debug-toggle').addEventListener('click', function () {
        const content = block.querySelector('.debug-content');
        const chevron = block.querySelector('.debug-chevron');
        const hidden = content.classList.toggle('hidden');
        chevron.textContent = hidden ? '▶' : '▼';
      });
      wrapper.appendChild(block);
    }
  } else {
    const bubble = document.createElement('div');
    bubble.className = 'bubble-system';
    bubble.textContent = text;
    wrapper.appendChild(bubble);
  }

  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
}

function simUpdateStats(stats) {
  const container = $('#sim-stats-row');
  if (!stats || !container) return;
  container.innerHTML = '';
  const cfg = state.simStatsConfig || {};
  for (const [name, value] of Object.entries(stats)) {
    const statCfg = cfg[name] || { min: 0, max: 100, direction: 'higher_is_better' };
    const min = statCfg.min ?? 0;
    const max = statCfg.max ?? 100;
    const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const good = statCfg.direction === 'lower_is_better' ? 1 - pct : pct;
    const color = good > 0.6 ? '#4ade80' : good > 0.3 ? '#f59e0b' : '#ef4444';
    const item = document.createElement('div');
    item.className = 'stat-item';
    item.innerHTML = `
      <div class="stat-label-row"><span>${escHtml(name)}</span><span>${value}</span></div>
      <div class="stat-track"><div class="stat-fill" style="width:${Math.round(pct * 100)}%;background:${color}"></div></div>
    `;
    container.appendChild(item);
  }
}

$('#sim-start-btn').addEventListener('click', async () => {
  const id = parseEditorJson()?.id || state.activeId;
  if (!id) {
    alert('请先选择或填写剧本');
    return;
  }
  const script = await resolveSimScriptPayload(id);
  if (!script) {
    alert('无法加载所选剧本');
    return;
  }
  const llmPayload = getDevLLMPayload();
  if (!llmPayload) {
    alert('请先在 模型配置中填写 API Base 和导演 Model');
    switchWorkspace('llm');
    $('#dev-llm-panel').classList.remove('hidden');
    $('#dev-llm-chevron').textContent = '▼';
    return;
  }
  syncPromptBufferFromEditor();
  const res = await fetch(`/api/dev/scripts/${id}/simulate/start`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      llm_config: llmPayload,
      script,
      prompt_overrides: getPromptBufferSnapshot(),
      prefer_saved_drafts: true,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('启动失败: ' + (err.detail || res.statusText));
    return;
  }
  const data = await res.json();
  state.simSessionId = data.session_id;
  state.simScriptId = id;
  state.simAiName = script.ai_character?.name || data.script?.ai_character_name || null;
  state.simStatsConfig = script.stats || data.script?.stats_config || null;
  state.simLlmConfig = data.llm_config || null;
  state.debugLog = [];

  $('#sim-messages').innerHTML = '';
  simAddMessage('system', `开始测试对局：${script.title || id}${state.scriptServerDraftSaved || state.dirtyIds.has(id) ? '（草稿）' : ''}${state.promptServerDraftSaved || promptBufferDiffersFromProduction() ? ' · Prompt 草稿' : ''}`);
  if (data.opening_line) simAddMessage('ai', data.opening_line);
  simUpdateStats(data.stats);
  resetStatTimeline(data.stats);

  $('#sim-input').disabled = false;
  $('#sim-send-btn').disabled = false;
  $('#sim-start-btn').classList.add('hidden');
  $('#sim-reset-btn').classList.remove('hidden');
  $('#sim-export-debug-btn').disabled = true;
});

$('#sim-reset-btn').addEventListener('click', () => {
  state.simSessionId = null;
  state.simAiName = null;
  state.simStatsConfig = null;
  state.simLlmConfig = null;
  state.debugLog = [];
  state.statTimeline = [];
  $('#sim-messages').innerHTML = '';
  $('#sim-stats-row').innerHTML = '';
  renderStatTimeline();
  $('#sim-input').disabled = true;
  $('#sim-send-btn').disabled = true;
  $('#sim-start-btn').classList.remove('hidden');
  $('#sim-reset-btn').classList.add('hidden');
  $('#sim-export-debug-btn').disabled = true;
});

function sanitizeLlmConfigForExport(cfg) {
  if (!cfg) return null;
  if (cfg.director || cfg.roleplay) return cfg;
  return {
    director: {
      provider: cfg.provider,
      api_base: cfg.api_base,
      model: cfg.director_model,
    },
    roleplay: {
      provider: cfg.provider,
      api_base: cfg.api_base,
      model: cfg.roleplay_model || cfg.director_model,
    },
  };
}

function exportDebugLog() {
  if (!state.debugLog.length && !state.statTimeline.length) return;
  const now = new Date();
  const ts = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    '_',
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
  ].join('');
  const payload = {
    script_id: state.simScriptId,
    exported_at: now.toISOString(),
    from_editor_draft: state.simScriptId ? state.dirtyIds.has(state.simScriptId) : false,
    llm_config: state.simLlmConfig || sanitizeLlmConfigForExport(getDevLLMPayload()),
    stat_timeline: state.statTimeline,
    turns: state.debugLog,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `debug_${state.simScriptId || 'session'}_${ts}.json`;
  a.click();
}

$('#sim-export-debug-btn').addEventListener('click', exportDebugLog);

async function simSend() {
  const input = $('#sim-input');
  const msg = input.value.trim();
  if (!msg || !state.simSessionId) return;
  input.value = '';
  simAddMessage('user', msg);

  const res = await fetch(`/api/dev/scripts/${state.simScriptId}/simulate/message`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.simSessionId, message: msg }),
  });
  if (!res.ok) {
    const err = await res.json();
    simAddMessage('system', '错误：' + (err.detail || '未知错误'));
    return;
  }
  const data = await res.json();
  simUpdateStats(data.stats);
  pushStatTimeline(data.turn, data.stats, data.stat_changes || {});

  if (data.game_over) {
    simAddMessage('system', `对局结束 · ${data.outcome === 'win' ? '胜利 🎉' : '失败'} · ${data.ending_text || ''}`);
    if (data._debug) {
      simAddMessage('ai', '', { turn: data.turn, debugData: data._debug, debugOnly: true });
    }
  } else {
    simAddMessage('ai', data.reply, {
      emotionTag: data.emotion_tag,
      turn: data.turn,
      debugData: data._debug,
    });
  }

  state.debugLog.push({
    turn: data.turn,
    player_message: msg,
    reply: data.game_over ? '' : data.reply,
    ending_text: data.ending_text,
    emotion_tag: data.emotion_tag,
    stats: data.stats,
    stat_changes: data.stat_changes,
    game_over: data.game_over,
    outcome: data.outcome,
    llm_config: data._debug?.llm_config || state.simLlmConfig,
    debug: data._debug,
  });
  $('#sim-export-debug-btn').disabled = false;

  if (data.game_over) {
    $('#sim-input').disabled = true;
    $('#sim-send-btn').disabled = true;
  }
}

$('#sim-send-btn').addEventListener('click', simSend);
$('#sim-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') simSend(); });

// ── Prompt editor ─────────────────────────────────────────────────────────────

let promptsLoaded = false;

async function ensurePromptsLoaded() {
  if (promptsLoaded) return;
  await loadPromptsFromServer();
  promptsLoaded = true;
}

async function loadPromptsFromServer() {
  const res = await fetch('/api/dev/prompts', { credentials: 'same-origin' });
  if (!res.ok) return;
  const data = await res.json();
  state.promptProduction = data.production || {};
  state.promptBuffer = { ...state.promptProduction };
  if (data.draft) {
    Object.assign(state.promptBuffer, data.draft);
    state.promptServerDraftSaved = true;
  } else {
    state.promptServerDraftSaved = false;
  }
  renderPromptNav();
  loadActivePromptIntoEditor();
  fillScriptSelects();
  updatePromptDraftStatus();
}

function renderPromptNav() {
  const nav = $('#prompt-nav');
  if (!nav) return;
  nav.innerHTML = '';
  for (const item of PROMPT_KEYS) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `prompt-nav-item${item.key === state.activePromptKey ? ' active' : ''}`;
    btn.innerHTML = `<span class="prompt-nav-label">${escHtml(item.agent)}</span>${escHtml(item.label.split(' · ')[1] || item.label)}`;
    btn.addEventListener('click', () => selectPromptKey(item.key));
    nav.appendChild(btn);
  }
}

function selectPromptKey(key) {
  syncPromptBufferFromEditor();
  state.activePromptKey = key;
  renderPromptNav();
  loadActivePromptIntoEditor();
}

function loadActivePromptIntoEditor() {
  const key = state.activePromptKey;
  const meta = PROMPT_KEYS.find((p) => p.key === key);
  $('#prompt-active-label').textContent = meta?.label || key;
  $('#prompt-textarea').value = state.promptBuffer[key] ?? state.promptProduction[key] ?? '';
}

async function resolvePreviewScript() {
  const selId = $('#prompt-script-select')?.value;
  if (selId && state.scripts[selId]) {
    try {
      const draftRes = await fetch(`/api/dev/drafts/scripts/${selId}`, { credentials: 'same-origin' });
      if (draftRes.ok) {
        const data = await draftRes.json();
        if (data.has_draft && data.draft) return data.draft;
      }
    } catch { /* fall through */ }
    const editorScript = parseEditorJson();
    if (editorScript?.id === selId) return editorScript;
    return state.scripts[selId];
  }
  const editorScript = parseEditorJson();
  if (editorScript?.id) return editorScript;
  return null;
}

async function previewPromptRender() {
  const script = await resolvePreviewScript();
  if (!script) {
    alert('请先选择剧本或在编辑器中打开一个剧本');
    return;
  }
  syncPromptBufferFromEditor();
  const playerMessage = $('#prompt-preview-message')?.value.trim()
    || '（示例玩家发言，用于预览 Prompt 渲染效果）';
  const res = await fetch('/api/dev/prompts/preview', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      script,
      prompts: getPromptBufferSnapshot(),
      player_message: playerMessage,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    alert('预览失败：' + (err.detail || res.statusText));
    return;
  }
  const data = await res.json();
  const body = $('#prompt-preview-body');
  body.innerHTML = `
    <div class="prompt-preview-block">
      <h4>导演 · system</h4>
      <pre>${escHtml(data.director?.system || '')}</pre>
    </div>
    <div class="prompt-preview-block">
      <h4>导演 · user</h4>
      <pre>${escHtml(data.director?.user || '')}</pre>
    </div>
    <div class="prompt-preview-block">
      <h4>演员 · system</h4>
      <pre>${escHtml(data.roleplay?.system || '')}</pre>
    </div>
    <div class="prompt-preview-block">
      <h4>演员 · user</h4>
      <pre>${escHtml(data.roleplay?.user || '')}</pre>
    </div>
  `;
}

$('#prompt-textarea')?.addEventListener('input', () => {
  state.promptServerDraftSaved = false;
  syncPromptBufferFromEditor();
  updatePromptDraftStatus();
  if (state.showPromptDiff) {
    const key = state.activePromptKey;
    renderDiffPanel(
      $('#prompt-diff-panel'),
      state.promptProduction[key] ?? '',
      state.promptBuffer[key] ?? '',
    );
  }
});

$('#prompt-draft-btn')?.addEventListener('click', async () => {
  syncPromptBufferFromEditor();
  const res = await fetch('/api/dev/prompts/draft', {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompts: getPromptBufferSnapshot() }),
  });
  if (!res.ok) {
    const err = await res.json();
    alert('保存 Prompt 草稿失败：' + (err.detail || res.statusText));
    return;
  }
  state.promptServerDraftSaved = true;
  updatePromptDraftStatus();
});

$('#prompt-publish-btn')?.addEventListener('click', async () => {
  if (!confirm('确定将 Prompt 草稿发布到生产环境？这将覆盖 prompts/ 目录下的正式模板。')) return;
  const res = await fetch('/api/dev/prompts/publish', {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const err = await res.json();
    alert('发布失败：' + (err.detail || '请先 Save Draft'));
    return;
  }
  await loadPromptsFromServer();
  state.promptServerDraftSaved = false;
  state.showPromptDiff = false;
  $('#prompt-diff-panel')?.classList.add('hidden');
  alert('Prompt 已发布到生产环境');
});

$('#prompt-diff-btn')?.addEventListener('click', () => {
  syncPromptBufferFromEditor();
  const panel = $('#prompt-diff-panel');
  state.showPromptDiff = !state.showPromptDiff;
  panel.classList.toggle('hidden', !state.showPromptDiff);
  if (!state.showPromptDiff) return;
  const key = state.activePromptKey;
  renderDiffPanel(
    panel,
    state.promptProduction[key] ?? '',
    state.promptBuffer[key] ?? '',
    '当前模板与生产版一致，无差异',
  );
});

$('#prompt-preview-btn')?.addEventListener('click', previewPromptRender);

// ── Bootstrap ─────────────────────────────────────────────────────────────────

$('#json-editor').addEventListener('input', () => {
  if (state.isNewDraft) {
    markEditorDirty();
    updateDetailHeader();
    renderScriptList();
    return;
  }
  if (state.activeId) {
    markEditorDirty();
    updateDetailHeader();
    renderScriptList();
  }
});

// ── Path calculator ───────────────────────────────────────────────────────────

function parseStatRange(spec) {
  if (typeof spec === 'number') return [spec, spec];
  if (Array.isArray(spec) && spec.length >= 2) {
    const lo = Number(spec[0]);
    const hi = Number(spec[1]);
    return lo <= hi ? [lo, hi] : [hi, lo];
  }
  return [0, 0];
}

function midpointDelta(spec) {
  const [lo, hi] = parseStatRange(spec);
  return Math.trunc((lo + hi) / 2);
}

function evaluateCondition(condition, stats) {
  if (!condition) return false;
  const parts = condition.trim().split(/\s*且\s*/);
  for (const part of parts) {
    const match = part.trim().match(/(.+?)\s*(<=|>=|<|>|==)\s*(-?\d+)/);
    if (!match) continue;
    const [, statName, op, rawValue] = match;
    const value = stats[statName.trim()] ?? 0;
    const threshold = Number(rawValue);
    if (op === '<=' && !(value <= threshold)) return false;
    if (op === '>=' && !(value >= threshold)) return false;
    if (op === '<' && !(value < threshold)) return false;
    if (op === '>' && !(value > threshold)) return false;
    if (op === '==' && !(value === threshold)) return false;
  }
  return true;
}

function computePathPreview(script, selectedKp, selectedPf) {
  const statsCfg = script.stats || {};
  const stats = Object.fromEntries(
    Object.entries(statsCfg).map(([name, cfg]) => [name, Number(cfg.initial ?? 0)])
  );
  const kpById = Object.fromEntries((script.key_points || []).map((kp) => [String(kp.id), kp]));
  const pfById = Object.fromEntries((script.pitfalls || []).map((pf) => [String(pf.id), pf]));

  for (const id of selectedKp) {
    const item = kpById[String(id)];
    if (!item) continue;
    for (const [stat, spec] of Object.entries(item.hit_stat_changes || {})) {
      if (stat in stats) stats[stat] += midpointDelta(spec);
    }
  }
  for (const id of selectedPf) {
    const item = pfById[String(id)];
    if (!item) continue;
    for (const [stat, spec] of Object.entries(item.hit_stat_changes || {})) {
      if (stat in stats) stats[stat] += midpointDelta(spec);
    }
  }

  for (const [name, value] of Object.entries(stats)) {
    const cfg = statsCfg[name] || {};
    const min = cfg.min ?? 0;
    const max = cfg.max ?? 100;
    stats[name] = Math.max(min, Math.min(max, value));
  }

  const wouldWin = evaluateCondition(script.win_condition || '', stats);
  const wouldLose = evaluateCondition(script.lose_condition || '', stats);
  const maxTurns = Number(script.max_turns ?? 15);
  const minTurnsNeeded = selectedKp.size;
  const turnMargin = maxTurns - minTurnsNeeded;

  let outcome = 'ongoing';
  if (wouldWin) outcome = 'win';
  else if (wouldLose) outcome = 'lose';

  return { stats, wouldWin, wouldLose, outcome, minTurnsNeeded, maxTurns, turnMargin, statsCfg };
}

function formatStatRanges(hitStatChanges) {
  if (!hitStatChanges) return '';
  return Object.entries(hitStatChanges).map(([stat, spec]) => {
    const [lo, hi] = parseStatRange(spec);
    return lo === hi ? `${stat} ${lo >= 0 ? '+' : ''}${lo}` : `${stat} [${lo}, ${hi}]`;
  }).join('；');
}

function renderPathCalculator() {
  const script = parseEditorJson();
  const kpContainer = $('#path-key-points');
  const pfContainer = $('#path-pitfalls');
  const paramsEl = $('#path-params');
  const statsGrid = $('#path-stats-grid');
  const outcomeEl = $('#path-outcome');

  if (!script || !script.stats) {
    paramsEl.textContent = '请在编辑器中加载有效剧本 JSON';
    kpContainer.innerHTML = '<div class="path-empty">—</div>';
    pfContainer.innerHTML = '<div class="path-empty">—</div>';
    statsGrid.innerHTML = '';
    outcomeEl.className = 'path-outcome ongoing';
    outcomeEl.textContent = '勾选下方关键点/减分点，查看假设结果';
    return;
  }

  const validKpIds = new Set((script.key_points || []).map((kp) => String(kp.id)));
  const validPfIds = new Set((script.pitfalls || []).map((pf) => String(pf.id)));
  state.pathSelectedKp = new Set([...state.pathSelectedKp].filter((id) => validKpIds.has(String(id))));
  state.pathSelectedPf = new Set([...state.pathSelectedPf].filter((id) => validPfIds.has(String(id))));

  paramsEl.innerHTML = `
    <span>max_turns: <strong>${script.max_turns ?? '—'}</strong></span>
    <span>胜利: ${escHtml(script.win_condition || '—')}</span>
    <span>失败: ${escHtml(script.lose_condition || '—')}</span>
  `;

  const renderChecks = (container, items, selectedSet, type) => {
    container.innerHTML = '';
    if (!items.length) {
      container.innerHTML = '<div class="path-empty">未配置</div>';
      return;
    }
    for (const item of items) {
      const id = String(item.id);
      const row = document.createElement('div');
      row.className = 'path-check-item';
      const title = item.title ? `[${item.title}] ` : '';
      row.innerHTML = `
        <input type="checkbox" id="path-${type}-${id}" ${selectedSet.has(id) ? 'checked' : ''}>
        <label for="path-${type}-${id}">
          <div>${escHtml(title)}${escHtml(item.description || id)}</div>
          <div class="path-check-meta">${escHtml(formatStatRanges(item.hit_stat_changes))}</div>
        </label>
      `;
      row.querySelector('input').addEventListener('change', (e) => {
        if (e.target.checked) selectedSet.add(id);
        else selectedSet.delete(id);
        renderPathCalculator();
      });
      container.appendChild(row);
    }
  };

  renderChecks(kpContainer, script.key_points || [], state.pathSelectedKp, 'kp');
  renderChecks(pfContainer, script.pitfalls || [], state.pathSelectedPf, 'pf');

  const preview = computePathPreview(script, state.pathSelectedKp, state.pathSelectedPf);
  statsGrid.innerHTML = Object.entries(preview.stats).map(([name, value]) => {
    const initial = preview.statsCfg[name]?.initial ?? '—';
    return `<div class="path-stat-card"><span>${escHtml(name)}</span><strong>${value}</strong><span style="color:var(--text-muted)">初始 ${initial}</span></div>`;
  }).join('');

  outcomeEl.className = `path-outcome ${preview.outcome}`;
  if (preview.outcome === 'win') {
    outcomeEl.textContent = `✓ 假设路径可达胜利条件 · 最少需 ${preview.minTurnsNeeded} 轮 · 余量 ${preview.turnMargin} 轮`;
  } else if (preview.outcome === 'lose') {
    outcomeEl.textContent = `✕ 假设路径会触发失败条件 · 已选 ${preview.minTurnsNeeded} 个关键点 · max_turns ${preview.maxTurns}`;
  } else {
    outcomeEl.textContent = `未达胜负条件 · 最少需 ${preview.minTurnsNeeded} 轮命中关键点 · 距 max_turns 余量 ${preview.turnMargin} 轮`;
  }
}

$('#login-btn').addEventListener('click', doLogin);
$('#login-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

init().then(() => {
  updateDetailHeader();
  renderPathCalculator();
});
