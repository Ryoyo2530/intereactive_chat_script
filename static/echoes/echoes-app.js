import {
  applyTonePreset,
  statPercent,
  shouldShowEcho,
  buildEchoCard,
  ECHO_THRESHOLD,
} from './echoes-core.js';

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

/** Organic path-spine SVG (water/ink feel). visitedCount >= 1. */
function buildSpineSvg(visitedCount, hadBranch) {
  const n = Math.max(1, Math.min(visitedCount, 8));
  const pts = [];
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0 : i / (n - 1);
    const x = 24 + t * 300;
    const y = 55 - Math.sin(t * Math.PI) * 18 - (i % 2 === 0 ? 0 : 6);
    pts.push([x, y]);
  }
  const current = pts[pts.length - 1];
  const fadeX = Math.min(440, current[0] + 100);
  const fadeY = current[1] - 18;
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1];
    const cur = pts[i];
    const cx = (prev[0] + cur[0]) / 2;
    d += ` C ${cx} ${prev[1]}, ${cx} ${cur[1]}, ${cur[0]} ${cur[1]}`;
  }
  d += ` C ${current[0] + 40} ${current[1] - 10}, ${fadeX - 20} ${fadeY + 8}, ${fadeX} ${fadeY}`;

  let trib = '';
  if (hadBranch && pts.length >= 2) {
    const branchAt = pts[Math.max(0, pts.length - 2)];
    trib = `<path d="M ${branchAt[0]} ${branchAt[1]} C ${branchAt[0] + 20} ${branchAt[1] + 22}, ${branchAt[0] + 45} ${branchAt[1] + 32}, ${branchAt[0] + 70} ${branchAt[1] + 36}"
          fill="none" stroke="url(#tribFade)" stroke-width="1" stroke-linecap="round"/>`;
  }

  const circles = pts.map((p, i) => {
    const isCurrent = i === pts.length - 1;
    if (isCurrent) {
      return `<circle cx="${p[0]}" cy="${p[1]}" r="5.5" fill="#F5F2EB" stroke="#4B6355" stroke-width="2"/>`;
    }
    return `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#4B6355"/>`;
  }).join('');

  return `<svg viewBox="0 0 480 90" class="echoes-spine-svg" aria-hidden="true">
    <defs>
      <linearGradient id="mainFade" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#4B6355" stop-opacity="1"/>
        <stop offset="55%" stop-color="#4B6355" stop-opacity="1"/>
        <stop offset="100%" stop-color="#4B6355" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="tribFade" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#B0AA9C" stop-opacity="0.55"/>
        <stop offset="100%" stop-color="#B0AA9C" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${d}" fill="none" stroke="url(#mainFade)" stroke-width="1.3" stroke-linecap="round"/>
    ${trib}
    ${circles}
    <text x="${pts[0][0]}" y="${pts[0][1] + 16}" font-size="8" fill="#A6A196" text-anchor="middle">起</text>
    <text x="${current[0]}" y="${current[1] - 12}" font-size="8" fill="#4B6355" text-anchor="middle">此刻</text>
  </svg>`;
}

export function echoesGame() {
  return {
    sessionId: null,
    script: null,
    stats: {},
    statsConfig: {},
    echoPhrases: null,
    chapterTitle: '',
    entries: [],
    inputText: '',
    busy: false,
    waitingForReply: false,
    gameOver: false,
    turn: 1,
    maxTurns: 15,
    aiName: '',
    playerName: '',
    entrySeq: 0,
    tonePreset: '从容',
    briefing: '',
    objective: '',
    aiIntro: '',
    playerPersona: '',
    contextCollapsed: false,
    hintsRemaining: 3,
    hintBusy: false,
    workType: 'short_form',
    visitedChapterIds: [],
    hadBranchChoice: false,
    chapterTransitionVisible: false,
    chapterTransitionTitle: '',
    // Chapter settlement (pending two-step advance)
    chapterSettlementVisible: false,
    chapterSettlementData: null,
    // Work ending overlay (terminal chapter / work completed)
    workEndingVisible: false,
    workEndingData: null,

    get isLongForm() {
      return this.workType === 'long_form';
    },

    get scriptTitle() {
      return this.script?.title || '未命名';
    },

    get displayTitle() {
      if (this.isLongForm && this.chapterTitle) return this.chapterTitle;
      return this.scriptTitle;
    },

    get turnHint() {
      return `· 第 ${this.turn} / ${this.maxTurns} 轮`;
    },

    get spineSvg() {
      return buildSpineSvg(this.visitedChapterIds.length || 1, this.hadBranchChoice);
    },

    get statRows() {
      return Object.entries(this.statsConfig).map(([name, cfg]) => {
        const value = this.stats[name] ?? cfg.initial ?? 0;
        const min = cfg.min ?? 0;
        const max = cfg.max ?? 100;
        return {
          name,
          label: cfg.label || name,
          value,
          percent: statPercent(value, min, max),
        };
      });
    },

    init() {
      window.addEventListener('echoes:session-started', (e) => {
        this.onSessionStarted(e.detail);
      });
      window.addEventListener('echoes:reset', () => this.reset());
    },

    reset() {
      this.sessionId = null;
      this.script = null;
      this.stats = {};
      this.statsConfig = {};
      this.echoPhrases = null;
      this.chapterTitle = '';
      this.entries = [];
      this.inputText = '';
      this.busy = false;
      this.waitingForReply = false;
      this.gameOver = false;
      this.turn = 1;
      this.maxTurns = 15;
      this.entrySeq = 0;
      this.briefing = '';
      this.objective = '';
      this.aiIntro = '';
      this.playerPersona = '';
      this.contextCollapsed = false;
      this.hintsRemaining = 3;
      this.hintBusy = false;
      this.workType = 'short_form';
      this.visitedChapterIds = [];
      this.hadBranchChoice = false;
      this.chapterTransitionVisible = false;
      this.chapterTransitionTitle = '';
      this.chapterSettlementVisible = false;
      this.chapterSettlementData = null;
      this.workEndingVisible = false;
      this.workEndingData = null;
    },

    applyScriptDetail(detail) {
      if (!detail) return;
      this.briefing = detail.briefing || '';
      this.objective = detail.objective || '';
      this.aiIntro = detail.ai_character?.intro || '';
      this.playerPersona = detail.player_character?.persona || '';
      if (detail.echo_phrases) this.echoPhrases = detail.echo_phrases;
      if (detail.tone_preset) {
        this.tonePreset = detail.tone_preset;
        applyTonePreset(this.tonePreset);
      }
      if (detail.chapter_title) this.chapterTitle = detail.chapter_title;
      if (detail.title && !this.chapterTitle) this.chapterTitle = detail.title;
    },

    async onSessionStarted(data) {
      this.reset();
      this.sessionId = data.session_id;
      this.script = data.script;
      this.stats = { ...data.stats };
      this.statsConfig = data.script.stats_config || {};
      this.turn = data.turn || 1;
      this.maxTurns = data.script.max_turns || 15;
      this.aiName = data.script.ai_character_name || '';
      this.playerName = data.script.player_character_name || '';
      this.chapterTitle = data.script.chapter_title || data.script.title || '';
      this.echoPhrases = data.script.echo_phrases || null;
      this.tonePreset = data.script.tone_preset || '从容';
      this.workType = data.script.work_type || data.work_type || 'short_form';
      this.visitedChapterIds = data.visited_chapter_ids || [];
      this.hadBranchChoice = !!data.had_branch_choice;
      applyTonePreset(this.tonePreset);

      if (data.scriptDetail) {
        this.applyScriptDetail(data.scriptDetail);
      } else if (data.script?.id) {
        await this.loadScriptDetail(data.script.id);
      }

      this.hintsRemaining = data.script?.max_hints ?? 3;
      this.hintBusy = false;
      this.contextCollapsed = false;

      if (data.resumed && Array.isArray(data.history) && data.history.length) {
        for (const h of data.history) {
          if (h.role === 'assistant') {
            this.appendEntry({ type: 'ai', text: h.content || '', emotion: '' });
          } else if (h.role === 'user') {
            this.appendEntry({ type: 'player', text: h.content || '' });
          }
        }
      } else if (data.opening_line) {
        this.appendEntry({ type: 'ai', text: data.opening_line, emotion: '' });
      }

      this.$nextTick(() => {
        document.querySelector('#screen-game .echoes-input')?.focus();
        this.scrollFlow();
      });
    },

    async playChapterTransition(title) {
      this.chapterTransitionTitle = title || '下一幕';
      this.chapterTransitionVisible = true;
      const ms = this.tonePreset === '明快' ? 550 : 1000;
      await new Promise((r) => setTimeout(r, ms));
      this.chapterTransitionVisible = false;
    },

    async applyLongFormAdvance(finalData) {
      const title = finalData.chapter_title || '下一幕';
      await this.playChapterTransition(title);
      this.chapterTitle = title;
      this.maxTurns = finalData.max_turns || this.maxTurns;
      this.turn = 0;
      this.visitedChapterIds = finalData.visited_chapter_ids || this.visitedChapterIds;
      this.hadBranchChoice = !!finalData.had_branch_choice || this.hadBranchChoice;
      this.entries = [];
      this.entrySeq = 0;
      this.stats = finalData.stats || this.stats;
      const opening = finalData.next_opening_line || finalData.reply;
      if (opening) this.appendAi(opening, '');
    },

    async loadScriptDetail(scriptId) {
      try {
        const res = await fetch(`/api/scripts/${scriptId}/detail`);
        if (!res.ok) return;
        this.applyScriptDetail(await res.json());
      } catch (_) { /* optional enrichment */ }
    },

    nextId() {
      this.entrySeq += 1;
      return `e-${this.entrySeq}`;
    },

    scrollFlow() {
      this.$nextTick(() => {
        const el = document.getElementById('echoes-flow');
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    appendEntry(partial) {
      const entry = { id: this.nextId(), ...partial };
      this.entries = [...this.entries, entry];
      this.scrollFlow();
      return entry;
    },

    appendPlayer(text) {
      return this.appendEntry({ type: 'player', text });
    },

    appendAi(text, emotion = '', streaming = false) {
      return this.appendEntry({ type: 'ai', text: text || '', emotion, streaming });
    },

    appendEcho(statChanges, hitKeyPoints) {
      if (!shouldShowEcho(statChanges, hitKeyPoints, ECHO_THRESHOLD)) return;
      const card = buildEchoCard(statChanges, this.echoPhrases, hitKeyPoints);
      if (!card) return;
      this.appendEntry({
        type: 'echo',
        phrase: card.phrase,
        deltas: card.deltas.map((d) => ({
          name: d.name,
          delta: d.delta,
          text: `${d.name} ${d.delta > 0 ? '+' : '−'}${Math.abs(d.delta)}`,
        })),
      });
    },

    async submitInput() {
      const text = this.inputText.trim();
      if (!text || this.busy || this.gameOver || !this.sessionId) return;
      this.inputText = '';
      await this.sendMessage(text);
    },

    async sendMessage(message) {
      if (!message.trim() || this.busy || this.gameOver) return;
      this.busy = true;
      this.contextCollapsed = true;
      this.appendPlayer(message);
      this.waitingForReply = true;

      let aiEntryIndex = -1;
      try {
        const res = await fetch('/api/session/message/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: this.sessionId, message }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Request failed');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let aiEntryIndex = -1;
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
              this.waitingForReply = false;
              if (!gotToken) {
                aiEntryIndex = this.entries.length;
                this.appendAi('', event.emotion_tag || '', true);
                gotToken = true;
              } else {
                this.entries[aiEntryIndex].emotion = event.emotion_tag || '';
              }
            } else if (event.type === 'token') {
              this.waitingForReply = false;
              if (!gotToken) {
                aiEntryIndex = this.entries.length;
                this.appendAi('', '', true);
                gotToken = true;
              }
              this.entries[aiEntryIndex].text += event.content;
              this.entries = [...this.entries];
              this.scrollFlow();
            } else if (event.type === 'done') {
              finalData = event;
            }
          }
        }

        if (!finalData) throw new Error('Stream ended without result');

        this.waitingForReply = false;

        const pendingAdvance = !!(finalData.pending_advance && finalData.next_chapter_id);
        const workDone = !!finalData.work_completed;

        if (pendingAdvance) {
          // Chapter ended — show settlement screen, don't auto-advance.
          if (aiEntryIndex >= 0) {
            this.entries = this.entries.slice(0, aiEntryIndex);
          }
          this.stats = finalData.stats || this.stats;
          this.chapterSettlementData = {
            chapterTitle: finalData.chapter_title || '本章',
            summary: finalData.chapter_summary || '',
            statChangesSummary: finalData.stat_changes_summary || [],
            nextChapterId: finalData.next_chapter_id,
            visitedCount: (finalData.visited_chapter_ids || this.visitedChapterIds).length,
            hadBranchChoice: !!finalData.had_branch_choice || this.hadBranchChoice,
          };
          this.chapterSettlementVisible = true;
          this.gameOver = true;
        } else if (workDone) {
          // Work completed — show ending overlay instead of short-form card.
          if (aiEntryIndex >= 0) {
            this.entries = this.entries.slice(0, aiEntryIndex);
          }
          this.stats = finalData.stats || this.stats;
          this.visitedChapterIds = finalData.visited_chapter_ids || this.visitedChapterIds;
          this.hadBranchChoice = !!finalData.had_branch_choice || this.hadBranchChoice;
          this.workEndingData = {
            chapterTitle: finalData.chapter_title || '终局',
            endingTone: finalData.ending_tone || 'bittersweet',
            isNewEnding: !!finalData.is_new_ending,
            summary: finalData.chapter_summary || '',
            stats: finalData.stats || this.stats,
            statsConfig: this.statsConfig,
            visitedCount: this.visitedChapterIds.length,
            hadBranchChoice: this.hadBranchChoice,
          };
          this.workEndingVisible = true;
          this.gameOver = true;
        } else {
          if (!gotToken && !finalData.game_over) {
            this.appendAi(finalData.reply, finalData.emotion_tag || '');
          } else if (aiEntryIndex >= 0) {
            const aiEntry = this.entries[aiEntryIndex];
            aiEntry.streaming = false;
            if (finalData.reply && aiEntry.text !== finalData.reply) {
              aiEntry.text = finalData.reply;
            }
            if (finalData.emotion_tag) aiEntry.emotion = finalData.emotion_tag;
            this.entries = [...this.entries];
          }

          this.stats = finalData.stats || this.stats;
          this.turn = finalData.turn ?? this.turn;

          if (!finalData.game_over) {
            const hits = [
              ...(finalData.hit_key_points || []),
              ...(finalData.hit_pitfalls || []),
            ];
            this.appendEcho(finalData.stat_changes, hits);
          }

          if (finalData.game_over) {
            this.gameOver = true;
            window.dispatchEvent(new CustomEvent('echoes:game-over', {
              detail: {
                outcome: finalData.outcome || finalData.result,
                ending_text: finalData.ending_text,
                turn: this.turn,
                maxTurns: this.maxTurns,
                stats: this.stats,
                script: this.script,
                entries: this.entries.map((e) => ({
                  type: e.type,
                  text: e.text,
                  emotion: e.emotion,
                  phrase: e.phrase,
                  deltas: e.deltas,
                })),
              },
            }));
          }
        }
      } catch (err) {
        console.error(err);
        this.waitingForReply = false;
        this.appendAi('对方似乎愣了一下，没能立刻接上话……稍后再试一次吧。', '');
      } finally {
        this.busy = false;
        this.waitingForReply = false;
        this.scrollFlow();
      }
    },

    async confirmAdvance() {
      if (!this.chapterSettlementData || !this.sessionId) return;
      const workId = this.script?.id;
      if (!workId) return;
      try {
        const headers = { 'Content-Type': 'application/json' };
        const token = window._supabaseSession?.access_token;
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const res = await fetch(`/api/works/${workId}/chapters/advance`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ session_id: this.sessionId }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Advance failed');
        }
        const data = await res.json();
        this.chapterSettlementVisible = false;
        this.chapterSettlementData = null;
        this.gameOver = false;
        await this.applyLongFormAdvance(data);
      } catch (err) {
        console.error('[confirmAdvance]', err);
      }
    },

    async restartWork() {
      const workId = this.script?.id;
      if (!workId) return;
      this.workEndingVisible = false;
      this.workEndingData = null;
      // Fire session-started-style reset by re-dispatching to app layer.
      window.dispatchEvent(new CustomEvent('echoes:restart-work', { detail: { work_id: workId } }));
    },

    exitGame() {
      window.dispatchEvent(new CustomEvent('echoes:exit'));
    },

    showHelp() {
      this.requestHint();
    },

    async requestHint() {
      if (!this.sessionId || this.gameOver || this.hintBusy || this.hintsRemaining <= 0) {
        if (this.hintsRemaining <= 0) {
          this.appendEntry({ type: 'hint', text: '本局提示次数已用完。' });
        }
        return;
      }
      this.hintBusy = true;
      try {
        const res = await fetch('/api/session/hint', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: this.sessionId }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '提示请求失败');
        this.hintsRemaining = data.hints_remaining ?? 0;
        this.appendEntry({ type: 'hint', text: data.hint });
      } catch (err) {
        console.error(err);
        this.appendEntry({ type: 'hint', text: err.message || '暂时无法获取提示，请稍后再试。' });
      } finally {
        this.hintBusy = false;
      }
    },
  };
}

window.echoesGame = echoesGame;

document.addEventListener('alpine:init', () => {
  window.Alpine.data('echoesGame', echoesGame);
});
