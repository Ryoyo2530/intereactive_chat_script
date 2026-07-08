// ── Constants ─────────────────────────────────────────────────────────────────

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
    intro: "角色简介，展示在入场须知页面"
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
  emotion_vocabulary: ["开心", "平静", "疑惑", "不满", "愤怒", "感动"],
  ending_titles: { win: "成功", lose: "失败" }
};

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  scripts: {},       // {id: full_dict}
  activeId: null,
  simSessionId: null,
  simScriptId: null,
  simAiName: null,
  simStatsConfig: null,
  pendingImportFile: null,
};

const $ = (sel) => document.querySelector(sel);

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDebugAgent(obj) {
  if (!obj) return '(无数据)';
  return Object.entries(obj).map(([k, v]) => {
    const val = (typeof v === 'object' && v !== null) ? JSON.stringify(v) : String(v);
    return `${k}: ${val}`;
  }).join('\n');
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
}

function renderScriptList() {
  const container = $('#script-items');
  container.innerHTML = '';
  const scripts = Object.values(state.scripts);
  if (scripts.length === 0) {
    container.innerHTML = '<div class="p-4 text-xs text-gray-400">暂无剧本</div>';
    return;
  }
  for (const s of scripts) {
    const div = document.createElement('div');
    div.className = 'script-item' + (s.id === state.activeId ? ' active' : '');
    div.dataset.id = s.id;
    const tagColor = s.origin_tag === '影视同人' ? 'background:#ede9fe;color:#5b21b6' : 'background:#fce7f3;color:#9d174d';
    div.innerHTML = `
      <div class="text-sm font-medium text-gray-800 truncate">${s.title || s.id}</div>
      <div class="flex items-center gap-1 mt-1">
        <span class="tag-chip" style="${tagColor}">${s.origin_tag || '未分类'}</span>
        <span class="text-xs text-gray-400 ml-auto">${s.id}</span>
      </div>
    `;
    div.addEventListener('click', () => selectScript(s.id));
    container.appendChild(div);
  }
}

function selectScript(id) {
  state.activeId = id;
  renderScriptList();
  const script = state.scripts[id];
  if (script) {
    $('#json-editor').value = JSON.stringify(script, null, 2);
    clearValidation();
  }
  // Update simulate panel
  $('#sim-script-label').textContent = script ? script.title : '未选择剧本';
  $('#sim-start-btn').disabled = !script;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => {
      const active = b.dataset.tab === tab;
      b.className = active
        ? 'tab-btn px-4 py-2 text-sm rounded-t-lg border border-b-0 border-gray-200 bg-white font-medium text-blue-600'
        : 'tab-btn px-4 py-2 text-sm rounded-t-lg text-gray-500 hover:text-gray-700';
    });
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.toggle('active', p.id === `tab-${tab}`);
    });
  });
});

// ── Validation ────────────────────────────────────────────────────────────────

function clearValidation() {
  $('#validation-result').classList.add('hidden');
  $('#validation-result').innerHTML = '';
}

function showValidation(result) {
  const container = $('#validation-result');
  container.innerHTML = '';
  const { errors, warnings } = result;
  if (errors.length === 0 && warnings.length === 0) {
    container.innerHTML = '<div class="text-xs text-green-700 py-2">✓ 校验通过，无问题</div>';
  }
  for (const e of errors) {
    const d = document.createElement('div');
    d.className = 'validation-item validation-error';
    d.textContent = '✕ ' + e;
    container.appendChild(d);
  }
  for (const w of warnings) {
    const d = document.createElement('div');
    d.className = 'validation-item validation-warning';
    d.textContent = '⚠ ' + w;
    container.appendChild(d);
  }
  container.classList.remove('hidden');
  return errors.length === 0;
}

function parseEditorJson() {
  try {
    return JSON.parse($('#json-editor').value);
  } catch {
    return null;
  }
}

$('#validate-btn').addEventListener('click', async () => {
  const script = parseEditorJson();
  if (!script) {
    showValidation({ errors: ['JSON 格式错误，无法解析'], warnings: [] });
    return;
  }
  const id = script.id || state.activeId || '__temp__';
  const res = await fetch(`/api/dev/scripts/${id}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(script),
  });
  const result = await res.json();
  showValidation(result);
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(script),
  });
  if (!res.ok) {
    const err = await res.json();
    showValidation({ errors: err.detail?.errors || [err.detail || '保存失败'], warnings: err.detail?.warnings || [] });
    return;
  }
  const data = await res.json();
  showValidation({ errors: [], warnings: data.warnings || [] });
  await loadScripts();
  selectScript(id);
});

// ── Delete ────────────────────────────────────────────────────────────────────

$('#delete-btn').addEventListener('click', async () => {
  if (!state.activeId) return;
  const script = state.scripts[state.activeId];
  if (!confirm(`确定删除剧本「${script?.title || state.activeId}」？此操作不可撤销。`)) return;
  const res = await fetch(`/api/dev/scripts/${state.activeId}`, { method: 'DELETE' });
  if (!res.ok) { alert('删除失败'); return; }
  state.activeId = null;
  $('#json-editor').value = '';
  clearValidation();
  await loadScripts();
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

$('#export-all-btn').addEventListener('click', async () => {
  const res = await fetch('/api/dev/export');
  if (!res.ok) { alert('导出失败'); return; }
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'scripts.zip';
  a.click();
});

// ── New script ────────────────────────────────────────────────────────────────

$('#new-script-btn').addEventListener('click', () => {
  state.activeId = null;
  renderScriptList();
  $('#json-editor').value = JSON.stringify(SCRIPT_TEMPLATE, null, 2);
  clearValidation();
  // Switch to editor tab
  document.querySelector('[data-tab="editor"]').click();
});

// ── Import ────────────────────────────────────────────────────────────────────

$('#import-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = '';
  state.pendingImportFile = file;

  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/dev/scripts/import', { method: 'POST', body: fd });

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
    $('#import-modal').classList.remove('hidden');
    return;
  }
  await loadScripts();
  selectScript(data.id);
});

$('#conflict-overwrite').addEventListener('click', async () => {
  $('#import-modal').classList.add('hidden');
  if (!state.pendingImportFile) return;
  const fd = new FormData();
  fd.append('file', state.pendingImportFile);
  const res = await fetch('/api/dev/scripts/import/overwrite', { method: 'POST', body: fd });
  state.pendingImportFile = null;
  if (!res.ok) { alert('覆盖失败'); return; }
  const data = await res.json();
  await loadScripts();
  selectScript(data.id);
});

$('#conflict-cancel').addEventListener('click', () => {
  $('#import-modal').classList.add('hidden');
  state.pendingImportFile = null;
});

// ── Simulate ──────────────────────────────────────────────────────────────────

function simAddMessage(role, text, opts = {}) {
  const { emotionTag = '', turn = null, debugData = null } = opts;
  const container = $('#sim-messages');
  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex;flex-direction:column;gap:6px;';

  if (role === 'user') {
    const bubble = document.createElement('div');
    bubble.className = 'bubble-user';
    bubble.innerHTML = `<div class="bubble-body">${escHtml(text)}</div>`;
    wrapper.appendChild(bubble);
  } else if (role === 'ai') {
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

    if (debugData) {
      const turnLabel = turn != null ? ` · 第 ${turn} 轮` : '';
      const block = document.createElement('div');
      block.className = 'debug-block';
      block.innerHTML = `
        <button class="debug-toggle">
          <span>调试信息${escHtml(turnLabel)}</span>
          <span class="debug-chevron">▼</span>
        </button>
        <div class="debug-content">
          <div class="debug-agent">
            <p class="debug-agent-title">导演 Agent</p>
            <pre>${escHtml(formatDebugAgent(debugData.director))}</pre>
          </div>
          <div class="debug-agent">
            <p class="debug-agent-title">演员 Agent</p>
            <pre>${escHtml(formatDebugAgent(debugData.roleplay))}</pre>
          </div>
        </div>
      `;
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
  const id = state.activeId;
  if (!id) return;
  const res = await fetch(`/api/dev/scripts/${id}/simulate/start`, { method: 'POST' });
  if (!res.ok) { alert('启动失败'); return; }
  const data = await res.json();
  state.simSessionId = data.session_id;
  state.simScriptId = id;
  state.simAiName = data.script?.ai_character_name || null;
  state.simStatsConfig = data.script?.stats_config || null;

  $('#sim-messages').innerHTML = '';
  simAddMessage('system', `开始测试对局：${state.scripts[id]?.title || id}`);
  if (data.opening_line) simAddMessage('ai', data.opening_line);
  simUpdateStats(data.stats);

  $('#sim-input').disabled = false;
  $('#sim-send-btn').disabled = false;
  $('#sim-start-btn').classList.add('hidden');
  $('#sim-reset-btn').classList.remove('hidden');
});

$('#sim-reset-btn').addEventListener('click', () => {
  state.simSessionId = null;
  state.simAiName = null;
  state.simStatsConfig = null;
  $('#sim-messages').innerHTML = '';
  $('#sim-stats-row').innerHTML = '';
  $('#sim-input').disabled = true;
  $('#sim-send-btn').disabled = true;
  $('#sim-start-btn').classList.remove('hidden');
  $('#sim-reset-btn').classList.add('hidden');
});

async function simSend() {
  const input = $('#sim-input');
  const msg = input.value.trim();
  if (!msg || !state.simSessionId) return;
  input.value = '';
  simAddMessage('user', msg);

  const res = await fetch(`/api/dev/scripts/${state.simScriptId}/simulate/message`, {
    method: 'POST',
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
  simAddMessage('ai', data.reply, {
    emotionTag: data.emotion_tag,
    turn: data.turn,
    debugData: data._debug,
  });

  if (data.game_over) {
    simAddMessage('system', `对局结束 · ${data.outcome === 'win' ? '胜利 🎉' : '失败'} · ${data.ending_text || ''}`);
    $('#sim-input').disabled = true;
    $('#sim-send-btn').disabled = true;
  }
}

$('#sim-send-btn').addEventListener('click', simSend);
$('#sim-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') simSend(); });

// ── Bootstrap ─────────────────────────────────────────────────────────────────

$('#login-btn').addEventListener('click', doLogin);
$('#login-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

init();
