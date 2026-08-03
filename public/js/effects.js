'use strict';

// Injects short-lived animated elements into the session stage.
const effects = (() => {
  // Effects render into a clipped, absolutely-positioned overlay so that
  // inserting/removing them never changes document height or triggers
  // browser scroll-anchoring (which would shift the whole stage).
  function layer() {
    return document.getElementById('fx-layer');
  }

  // Spawn an element, remove it after its animation finishes.
  function spawn(el, lifeMs) {
    layer().appendChild(el);
    setTimeout(() => el.remove(), lifeMs);
  }

  // Slight random horizontal offset so repeated presses don't stack exactly.
  function jitter() {
    return (Math.random() * 80 - 40).toFixed(0);
  }

  return {
    coin() {
      const el = document.createElement('div');
      el.className = 'fx fx-coin';
      el.style.marginLeft = jitter() + 'px';
      el.textContent = '$';
      spawn(el, 950);
    },
    plus5() {
      const el = document.createElement('div');
      el.className = 'fx fx-box';
      el.style.marginLeft = jitter() + 'px';
      el.textContent = '+5';
      spawn(el, 950);
    },
    plus10() {
      const el = document.createElement('div');
      el.className = 'fx fx-box big';
      el.style.marginLeft = jitter() + 'px';
      el.textContent = '+10';
      spawn(el, 950);
    },
  };
})();
