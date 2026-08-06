'use strict';

// Entry point: switches between the three views and wires up the DOM controls
// that no other module owns. Loaded last, after every module it calls into.
(() => {
  const VIEW_IDS = ['view-login', 'view-dashboard', 'view-session'];

  const el = (id) => document.getElementById(id);

  function showView(id) {
    VIEW_IDS.forEach((v) => el(v).classList.toggle('hidden', v !== id));
  }

  function showLogin() {
    showView('view-login');
    el('password').value = '';
    el('login-error').classList.add('hidden');
  }

  // Always refetches, so totals are current after a session commits points.
  async function showDashboard() {
    showView('view-dashboard');
    try {
      await students.refresh();
    } catch (err) {
      window.alert('Failed to load students: ' + err.message);
    }
  }

  // --- Login / logout ---
  el('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const error = el('login-error');
    error.classList.add('hidden');
    try {
      await api.login(el('password').value);
    } catch (err) {
      error.textContent = err.status === 401 ? 'Wrong password' : err.message;
      error.classList.remove('hidden');
      return;
    }
    el('password').value = '';
    await showDashboard();
  });

  el('logout-btn').addEventListener('click', async () => {
    try {
      await api.logout();
    } finally {
      // Drop to the login screen either way; a failed logout still means the
      // teacher wants off this screen.
      showLogin();
    }
  });

  // --- Students ---
  el('create-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = el('new-student-name');
    const name = input.value.trim();
    if (!name) return;
    try {
      await students.onCreate(name);
      input.value = '';
    } catch (err) {
      window.alert('Failed to add student: ' + err.message);
    }
  });

  // --- Session ---
  el('start-session-btn').addEventListener('click', () => {
    const id = students.selectedId();
    const student = id === null ? null : students.getById(id);
    if (!student) {
      window.alert('Pick a student first.');
      return;
    }
    showView('view-session');
    session.start(student, showDashboard);
  });

  el('stop-session-btn').addEventListener('click', () => {
    session.stop();
  });

  // --- Timer (independent of the session; set and cleared from its view) ---
  el('timer-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const input = el('timer-input');
    if (!timer.start(input.value)) {
      window.alert('Could not read that time. Try 6:00, 90 or "5 minutes".');
      return;
    }
    input.value = '';
    // Points are awarded on a document-level keydown, so leaving the field
    // focused would also type z/x/c into it.
    input.blur();
  });

  el('clear-timer-btn').addEventListener('click', () => {
    timer.hide();
    el('timer-input').value = '';
  });

  // --- Boot ---
  // The session cookie survives a reload, so skip the login screen if it is
  // still valid.
  (async () => {
    try {
      const { loggedIn } = await api.checkSession();
      if (loggedIn) {
        await showDashboard();
        return;
      }
    } catch (_) {
      /* unreachable server: fall through to the login screen */
    }
    showLogin();
  })();
})();
