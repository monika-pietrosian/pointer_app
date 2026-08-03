'use strict';

// Student list rendering + CRUD wiring for the dashboard.
const students = (() => {
  let cache = [];

  const listEl = () => document.getElementById('student-list');
  const selectEl = () => document.getElementById('active-student');

  function getCache() {
    return cache;
  }

  function getById(id) {
    return cache.find((s) => s.id === Number(id)) || null;
  }

  function renderList() {
    const ul = listEl();
    ul.innerHTML = '';
    if (cache.length === 0) {
      const li = document.createElement('li');
      li.className = 'hint';
      li.textContent = 'No students yet. Add one above.';
      ul.appendChild(li);
    }
    cache.forEach((s) => {
      const li = document.createElement('li');
      li.className = 'student-row';
      li.innerHTML = `
        <span class="s-name" title="${escapeHtml(s.name)}">${escapeHtml(s.name)}</span>
        <span class="s-points">${s.points} pts</span>
        <button class="icon-btn edit" title="Rename">edit</button>
        <button class="icon-btn del" title="Delete">x</button>
      `;
      li.querySelector('.edit').addEventListener('click', () => onRename(s));
      li.querySelector('.del').addEventListener('click', () => onDelete(s));
      ul.appendChild(li);
    });
  }

  function renderSelect() {
    const sel = selectEl();
    const prev = sel.value;
    sel.innerHTML = '';
    if (cache.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— no students —';
      sel.appendChild(opt);
      return;
    }
    cache.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = String(s.id);
      opt.textContent = `${s.name} (${s.points})`;
      sel.appendChild(opt);
    });
    if (prev && cache.some((s) => String(s.id) === prev)) sel.value = prev;
  }

  async function refresh() {
    cache = await api.listStudents();
    renderList();
    renderSelect();
  }

  async function onCreate(name) {
    await api.createStudent(name);
    await refresh();
  }

  async function onRename(student) {
    const name = window.prompt('New name:', student.name);
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    await api.updateStudent(student.id, { name: trimmed });
    await refresh();
  }

  async function onDelete(student) {
    if (!window.confirm(`Delete ${student.name}? This removes their points too.`)) return;
    await api.deleteStudent(student.id);
    await refresh();
  }

  function selectedId() {
    const v = selectEl().value;
    return v ? Number(v) : null;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[c]));
  }

  return { refresh, onCreate, selectedId, getById, getCache };
})();
