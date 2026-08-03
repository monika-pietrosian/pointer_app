'use strict';

// Web Audio synthesis — no external sound files needed.
// To use recorded clips instead, load buffers and play them in place of
// the synth functions below (keep the same public method names).
const sfx = (() => {
  let ctx = null;

  function ac() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
    }
    // Browsers require a user gesture before audio can start.
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // Play a single tone with an envelope.
  function tone(freq, start, dur, type, gainPeak) {
    const c = ac();
    const t0 = c.currentTime + start;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = type || 'square';
    osc.frequency.setValueAtTime(freq, t0);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(gainPeak || 0.2, t0 + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  // Glide from f1 to f2 (for celebratory "wow"/"yeah" sweeps).
  function sweep(f1, f2, start, dur, type, gainPeak) {
    const c = ac();
    const t0 = c.currentTime + start;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = type || 'sawtooth';
    osc.frequency.setValueAtTime(f1, t0);
    osc.frequency.exponentialRampToValueAtTime(f2, t0 + dur);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(gainPeak || 0.2, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  return {
    // Must be called once from a user gesture to unlock audio.
    unlock() {
      ac();
    },
    // Z / +1 — classic two-note coin "money" blip.
    coin() {
      tone(988, 0, 0.08, 'square', 0.18); // B5
      tone(1319, 0.08, 0.18, 'square', 0.18); // E6
    },
    // X / +5 — "yeah" rising triad.
    yeah() {
      tone(523, 0, 0.1, 'square', 0.16); // C5
      tone(659, 0.09, 0.1, 'square', 0.16); // E5
      tone(784, 0.18, 0.22, 'square', 0.18); // G5
    },
    // C / +10 — "wow" big sweep + sparkle.
    wow() {
      sweep(330, 990, 0, 0.35, 'sawtooth', 0.16);
      tone(1175, 0.18, 0.12, 'square', 0.14); // D6
      tone(1568, 0.3, 0.25, 'square', 0.16); // G6
    },
    // Timer warnings: level 1=60s, 2=30s, 3=10s (more urgent each time).
    warn(level) {
      if (level === 1) {
        tone(660, 0, 0.18, 'square', 0.2);
      } else if (level === 2) {
        tone(660, 0, 0.12, 'square', 0.2);
        tone(660, 0.16, 0.12, 'square', 0.2);
      } else {
        tone(880, 0, 0.1, 'square', 0.22);
        tone(880, 0.13, 0.1, 'square', 0.22);
        tone(880, 0.26, 0.14, 'square', 0.22);
      }
    },
    // Time's up.
    timeUp() {
      sweep(880, 220, 0, 0.6, 'sawtooth', 0.2);
    },
  };
})();
