/**
 * Site credit + share/export helpers (v1.4).
 * Snapshot export only — not a resumable session link.
 */

export const SITE_CREDIT = {
  brand: '入戏',
  author: 'Ryoyo',
  contact: '📮selina2530@163.com',
  disclaimer: '内容由AI生成，仅供娱乐体验',
  fanficNote: '非原作品官方内容，人物为同人演绎',
  feedbackUrl: '',
  feedbackLabel: '觉得哪里怪？欢迎私信',
  /** Canonical public URL used in share copy when not on that host */
  siteUrl: 'https://ruxi.onrender.com',
};

export function creditLine() {
  return `${SITE_CREDIT.brand} · by ${SITE_CREDIT.author}`;
}

/** Prefer current origin on deployed hosts; fall back to configured siteUrl. */
export function getShareUrl() {
  try {
    const { origin, hostname } = window.location;
    if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
      return origin;
    }
  } catch (_) { /* ignore */ }
  return SITE_CREDIT.siteUrl || 'https://ruxi.onrender.com';
}

export function performanceId(scriptId) {
  const short = String(scriptId || 'play').replace(/[^a-zA-Z0-9_]/g, '').slice(-12) || 'play';
  const stamp = String(Date.now()).slice(-6);
  return `第 ${short}-${stamp} 场`;
}

function pickTopEchoes(echoes, limit = 2) {
  if (!Array.isArray(echoes) || !echoes.length) return [];
  const scored = echoes.map((e) => {
    const mag = (e.deltas || []).reduce((s, d) => s + Math.abs(Number(d.delta) || 0), 0);
    return { ...e, _mag: mag };
  });
  scored.sort((a, b) => b._mag - a._mag);
  return scored.slice(0, limit);
}

function ensureCaptureRoot() {
  let root = document.getElementById('share-capture-root');
  if (root) return root;
  root = document.createElement('div');
  root.id = 'share-capture-root';
  root.setAttribute('aria-hidden', 'true');
  document.body.appendChild(root);
  return root;
}

function buildEssenceDom(payload) {
  const { title, endingTitle, endingText, stats, echoes, originTag, perfId } = payload;
  const topEchoes = pickTopEchoes(echoes, 2);
  const statsHtml = Object.entries(stats || {})
    .map(([name, value]) => `<div class="share-stat"><span>${escapeHtml(name)}</span><strong>${escapeHtml(String(value))}</strong></div>`)
    .join('');
  const echoesHtml = topEchoes
    .map((e) => {
      const deltas = (e.deltas || []).map((d) => d.text).join('　');
      return `<aside class="share-echo"><p class="share-echo-phrase">${escapeHtml(e.phrase || '')}</p><p class="share-echo-deltas">${escapeHtml(deltas)}</p></aside>`;
    })
    .join('');
  const fanfic = originTag === '影视同人'
    ? `<p class="share-note">${escapeHtml(SITE_CREDIT.fanficNote)}</p>`
    : '';

  const el = document.createElement('div');
  el.className = 'share-card share-card-essence';
  el.innerHTML = `
    <p class="share-brand">${escapeHtml(SITE_CREDIT.brand)}</p>
    <h2 class="share-title">${escapeHtml(title || '')}</h2>
    <h3 class="share-ending-title">${escapeHtml(endingTitle || '')}</h3>
    <p class="share-ending-text">${escapeHtml(endingText || '')}</p>
    <div class="share-stats">${statsHtml}</div>
    ${echoesHtml}
    ${fanfic}
    <p class="share-perf">${escapeHtml(perfId || '')}</p>
    <p class="share-watermark">${escapeHtml(creditLine())}</p>
    <p class="share-disclaimer">${escapeHtml(SITE_CREDIT.disclaimer)}</p>
  `;
  return el;
}

function buildFullDom(payload) {
  const { title, entries, aiName, playerName, perfId } = payload;
  const lines = (entries || []).map((entry) => {
    if (entry.type === 'ai') {
      const emo = entry.emotion ? `<p class="share-flow-emotion">${escapeHtml(entry.emotion)}</p>` : '';
      return `<div class="share-flow-entry">${emo}<p><span class="share-speaker">${escapeHtml((aiName || '对方') + '：')}</span>${escapeHtml(entry.text || '')}</p></div>`;
    }
    if (entry.type === 'player') {
      return `<div class="share-flow-entry share-flow-player"><p><span class="share-speaker">${escapeHtml((playerName || '你') + '：')}</span>${escapeHtml(entry.text || '')}</p></div>`;
    }
    if (entry.type === 'echo') {
      const deltas = (entry.deltas || []).map((d) => d.text).join('　');
      return `<aside class="share-echo"><p class="share-echo-phrase">${escapeHtml(entry.phrase || '')}</p><p class="share-echo-deltas">${escapeHtml(deltas)}</p></aside>`;
    }
    if (entry.type === 'hint') {
      return `<aside class="share-hint"><p>提示</p><p>${escapeHtml(entry.text || '')}</p></aside>`;
    }
    return '';
  }).join('');

  const el = document.createElement('div');
  el.className = 'share-card share-card-full';
  el.innerHTML = `
    <p class="share-brand">${escapeHtml(SITE_CREDIT.brand)}</p>
    <h2 class="share-title">${escapeHtml(title || '')}</h2>
    <p class="share-note">完整回顾 · 较长图片</p>
    <div class="share-flow">${lines}</div>
    <p class="share-perf">${escapeHtml(perfId || '')}</p>
    <p class="share-watermark">${escapeHtml(creditLine())}</p>
    <p class="share-disclaimer">${escapeHtml(SITE_CREDIT.disclaimer)}</p>
  `;
  return el;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function waitForFonts() {
  if (document.fonts?.ready) {
    try {
      await document.fonts.ready;
    } catch (_) { /* ignore */ }
  }
}

async function loadHtml2Canvas() {
  if (window.html2canvas) return window.html2canvas;
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('html2canvas 加载失败'));
    document.head.appendChild(s);
  });
  return window.html2canvas;
}

async function captureElement(el, filename) {
  await waitForFonts();
  const html2canvas = await loadHtml2Canvas();
  const root = ensureCaptureRoot();
  root.innerHTML = '';
  root.appendChild(el);
  // Force layout before capture
  void el.offsetHeight;
  const canvas = await html2canvas(el, {
    backgroundColor: '#F5F2EB',
    scale: Math.min(2, window.devicePixelRatio || 1.5),
    useCORS: true,
    logging: false,
  });
  root.innerHTML = '';
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      resolve({ blob, canvas, filename });
    }, 'image/png');
  });
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function downloadText(text, filename) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  downloadBlob(blob, filename);
}

export function buildShareCopy(payload) {
  const title = payload.title || '入戏';
  const ending = payload.endingTitle || payload.endingText || '';
  const url = getShareUrl();
  return [
    `我刚在「${SITE_CREDIT.brand}」演完一局《${title}》`,
    ending ? `结局：${ending}` : '',
    `来玩：🔗 ${url}`,
    '（链接是体验入口，不是可续玩的本局）',
  ].filter(Boolean).join('\n');
}

export function buildTranscriptText(payload) {
  const lines = [
    `《${payload.title || ''}》`,
    payload.endingTitle ? `结局：${payload.endingTitle}` : '',
    payload.endingText || '',
    '',
  ];
  for (const entry of payload.entries || []) {
    if (entry.type === 'ai') {
      if (entry.emotion) lines.push(`（${entry.emotion}）`);
      lines.push(`${payload.aiName || '对方'}：${entry.text || ''}`);
    } else if (entry.type === 'player') {
      lines.push(`${payload.playerName || '你'}：${entry.text || ''}`);
    } else if (entry.type === 'echo') {
      const deltas = (entry.deltas || []).map((d) => d.text).join(' ');
      lines.push(`[世界残响] ${entry.phrase || ''} ${deltas}`.trim());
    } else if (entry.type === 'hint') {
      lines.push(`[提示] ${entry.text || ''}`);
    }
    lines.push('');
  }
  lines.push(creditLine());
  lines.push(SITE_CREDIT.disclaimer);
  return lines.filter((l, i, arr) => !(l === '' && arr[i - 1] === '')).join('\n');
}

export async function exportEssenceImage(payload) {
  const el = buildEssenceDom(payload);
  const safe = (payload.title || 'ruxi').replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 24);
  return captureElement(el, `入戏-${safe}-精华.png`);
}

export async function exportFullImage(payload) {
  const el = buildFullDom(payload);
  const safe = (payload.title || 'ruxi').replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 24);
  return captureElement(el, `入戏-${safe}-完整回顾.png`);
}

export async function shareOrDownload({ blob, filename }, copyText) {
  const file = new File([blob], filename, { type: 'image/png' });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: SITE_CREDIT.brand, text: copyText });
      return 'shared';
    } catch (err) {
      if (err && err.name === 'AbortError') return 'aborted';
    }
  }
  downloadBlob(blob, filename);
  return 'downloaded';
}

export function exportTranscript(payload) {
  const safe = (payload.title || 'ruxi').replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 24);
  downloadText(buildTranscriptText(payload), `入戏-${safe}.txt`);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    return false;
  }
}
