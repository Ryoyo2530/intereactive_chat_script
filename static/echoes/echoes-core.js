/** Shared Echoes reading-flow utilities (v1.3) */

export const ECHO_THRESHOLD = 5;

export const TONE_PRESETS = {
  从容: {
    lineHeight: '1.9',
    letterSpacing: '0.03em',
    replyDuration: '450ms',
    echoDuration: '300ms',
  },
  明快: {
    lineHeight: '1.6',
    letterSpacing: 'normal',
    replyDuration: '175ms',
    echoDuration: '150ms',
  },
};

export const DEFAULT_ECHO_PHRASES = {
  _default: {
    up_small: ['有什么东西轻轻动了一下。', '局势有了细微的变化。'],
    up_medium: ['空气里多了一些张力。', '关系的天平开始倾斜。'],
    up_large: ['世界猛然一紧。', '气氛骤然改变。'],
    down_small: ['紧绷稍稍松了半分。', '有什么东西安静下来了。'],
    down_medium: ['空气松弛了一瞬。', '紧绷的气氛稍稍缓和。'],
    down_large: ['重压忽然卸去一角。', '她似乎松了一口气。'],
  },
};

export function applyTonePreset(presetName) {
  const preset = TONE_PRESETS[presetName] || TONE_PRESETS['从容'];
  const root = document.documentElement;
  root.style.setProperty('--reading-line-height', preset.lineHeight);
  root.style.setProperty('--reading-letter-spacing', preset.letterSpacing);
  root.style.setProperty('--anim-reply-duration', preset.replyDuration);
  root.style.setProperty('--anim-echo-duration', preset.echoDuration);
}

export function statPercent(value, min, max) {
  const span = max - min;
  if (span <= 0) return 50;
  return Math.max(0, Math.min(100, ((value - min) / span) * 100));
}

export function magnitudeOfDelta(delta) {
  const abs = Math.abs(delta);
  if (abs >= 10) return 'large';
  if (abs >= 5) return 'medium';
  return 'small';
}

export function shouldShowEcho(statChanges, hitKeyPoints, threshold = ECHO_THRESHOLD) {
  const changes = statChanges || {};
  if (Object.values(changes).some((d) => Math.abs(Number(d) || 0) >= threshold)) {
    return true;
  }
  if (Array.isArray(hitKeyPoints) && hitKeyPoints.length > 0) {
    return true;
  }
  return false;
}

export function pickEchoPhrase(statName, delta, echoPhrases) {
  const direction = delta >= 0 ? 'up' : 'down';
  const magnitude = magnitudeOfDelta(delta);
  const key = `${direction}_${magnitude}`;

  const pools = echoPhrases?.[statName] || echoPhrases?._default || DEFAULT_ECHO_PHRASES._default;
  const list = pools[key] || pools[`${direction}_medium`] || DEFAULT_ECHO_PHRASES._default[key] || ['世界有了细微的变化。'];
  return list[Math.floor(Math.random() * list.length)];
}

export function buildEchoCard(statChanges, echoPhrases, hitKeyPoints) {
  const changes = Object.entries(statChanges || {}).filter(([, d]) => Number(d) !== 0);
  if (!changes.length && (!hitKeyPoints || !hitKeyPoints.length)) {
    return null;
  }

  const primary = changes.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
  const phrase = primary
    ? pickEchoPhrase(primary[0], primary[1], echoPhrases)
    : '有什么关键的事发生了。';

  const deltas = changes.map(([name, delta]) => ({
    name,
    delta: Number(delta),
    text: formatStatDelta(name, Number(delta)),
  }));

  return { phrase, deltas };
}

export function formatStatDelta(name, delta) {
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '';
  const num = Math.abs(delta);
  return { name, delta, label: `${name} ${sign}${num}` };
}

export function formatChapterLabel(turn, chapterTitle) {
  const chapterNum = String(turn).padStart(2, '0');
  return `Chapter ${chapterNum} / ${chapterTitle}`;
}
