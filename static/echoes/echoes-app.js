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

    get scriptTitle() {
      return this.script?.title || '未命名';
    },

    get turnHint() {
      return `· 第 ${this.turn} / ${this.maxTurns} 轮`;
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
      applyTonePreset(this.tonePreset);

      if (data.scriptDetail) {
        this.applyScriptDetail(data.scriptDetail);
      } else if (data.script?.id) {
        await this.loadScriptDetail(data.script.id);
      }

      this.hintsRemaining = data.script?.max_hints ?? 3;
      this.hintBusy = false;
      this.contextCollapsed = false;

      if (data.opening_line) {
        this.appendEntry({ type: 'ai', text: data.opening_line, emotion: '' });
      }

      this.$nextTick(() => {
        document.querySelector('#screen-game .echoes-input')?.focus();
        this.scrollFlow();
      });
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
