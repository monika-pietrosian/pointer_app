'use strict';

// Active session: one student, live point awards via z/x/c, commit on stop.
const session = (() => {
  let active = null; // { id, name, basePoints }
  let sessionPoints = 0;
  let onEnd = null; // callback to return to dashboard

  const scoreEl = () => document.getElementById('score-display');

  function renderScore() {
    const total = (active ? active.basePoints : 0) + sessionPoints;
    const el = scoreEl();
    el.textContent = `${active ? active.name : 'Name'}: ${total}`;
    el.classList.remove('bump');
    // reflow to restart animation
    void el.offsetWidth;
    el.classList.add('bump');
  }

  function award(points, kind) {
    if (!active) return;
    sessionPoints += points;
    if (kind === 'coin') {
      effects.coin();
      sfx.coin();
    } else if (kind === 'plus5') {
      effects.plus5();
      sfx.yeah();
    } else if (kind === 'plus10') {
      effects.plus10();
      sfx.wow();
    }
    renderScore();
  }

  function onKey(e) {
    if (!active) return;
    const k = e.key.toLowerCase();
    if (k === 'z') {
      award(1, 'coin');
    } else if (k === 'x') {
      award(5, 'plus5');
    } else if (k === 'c') {
      award(10, 'plus10');
    }
  }

  // student: {id, name, points}. The timer is independent and controlled
  // separately from inside the session view.
  function start(student, endCallback) {
    active = { id: student.id, name: student.name, basePoints: student.points };
    sessionPoints = 0;
    onEnd = endCallback;
    sfx.unlock(); // unlock audio on the user gesture that started the session
    renderScore();
    document.addEventListener('keydown', onKey);
  }

  async function stop() {
    document.removeEventListener('keydown', onKey);
    timer.hide(); // stopping the session also stops any running timer
    const earned = sessionPoints;
    const id = active ? active.id : null;
    active = null;
    sessionPoints = 0;
    if (id !== null && earned !== 0) {
      try {
        await api.addPoints(id, earned);
      } catch (err) {
        window.alert('Failed to save points: ' + err.message);
      }
    }
    if (onEnd) onEnd();
  }

  return { start, stop };
})();
