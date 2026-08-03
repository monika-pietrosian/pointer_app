'use strict';

// e.ggtimer-style countdown with a shrinking heart bar and audible warnings.
const timer = (() => {
  let totalSec = 0;
  let remaining = 0;
  let intervalId = null;
  let firedWarnings = {};

  const wrap = () => document.getElementById('timer-wrap');
  const fill = () => document.getElementById('timer-fill');
  const display = () => document.getElementById('timer-display');

  // Parse flexible input: "90", "6:00", "1:30:00", "5 minutes", "30 sec".
  function parse(input) {
    if (!input) return 0;
    const s = String(input).trim().toLowerCase();
    if (!s) return 0;

    // "5 minutes" / "30 seconds" / "1 hour" word forms
    const word = s.match(/^(\d+)\s*(h|hour|hours|m|min|minute|minutes|s|sec|second|seconds)\b/);
    if (word) {
      const n = parseInt(word[1], 10);
      const unit = word[2];
      if (unit.startsWith('h')) return n * 3600;
      if (unit.startsWith('s')) return n;
      return n * 60; // minutes
    }

    // "mm:ss" or "hh:mm:ss"
    if (s.includes(':')) {
      const parts = s.split(':').map((p) => parseInt(p, 10) || 0);
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      if (parts.length === 2) return parts[0] * 60 + parts[1];
    }

    // bare number => minutes (matches e.ggtimer.com default)
    const num = parseInt(s, 10);
    if (!isNaN(num)) return num * 60;
    return 0;
  }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
    const pad = (n) => String(n).padStart(2, '0');
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${mm}:${pad(s)}`;
  }

  function render() {
    display().textContent = fmt(remaining);
    const pct = totalSec > 0 ? (remaining / totalSec) * 100 : 0;
    fill().style.width = pct + '%';
    wrap().classList.toggle('warn', remaining <= 60 && remaining > 10);
    wrap().classList.toggle('danger', remaining <= 10);
  }

  function tick() {
    remaining -= 1;
    if (remaining === 60 && !firedWarnings[60]) {
      firedWarnings[60] = true;
      sfx.warn(1);
    } else if (remaining === 30 && !firedWarnings[30]) {
      firedWarnings[30] = true;
      sfx.warn(2);
    } else if (remaining === 10 && !firedWarnings[10]) {
      firedWarnings[10] = true;
      sfx.warn(3);
    }
    if (remaining <= 0) {
      remaining = 0;
      render();
      stop();
      sfx.timeUp();
      // Reset to idle shortly after, so it can be started again.
      setTimeout(reset, 1200);
      return;
    }
    render();
  }

  // Return to a clean idle state (bar hidden, ready for a fresh start).
  function reset() {
    stop();
    totalSec = 0;
    remaining = 0;
    firedWarnings = {};
    wrap().classList.remove('warn', 'danger');
    fill().style.width = '100%';
    display().textContent = '0:00';
    wrap().classList.add('hidden');
  }

  // Start the timer from a parsed-seconds input. Returns false if no valid time.
  function start(input) {
    const sec = parse(input);
    if (sec <= 0) {
      wrap().classList.add('hidden');
      return false;
    }
    stop();
    totalSec = sec;
    remaining = sec;
    firedWarnings = {};
    wrap().classList.remove('hidden');
    render();
    intervalId = setInterval(tick, 1000);
    return true;
  }

  function stop() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  }

  function hide() {
    stop();
    wrap().classList.add('hidden');
  }

  return { start, stop, hide, parse };
})();
