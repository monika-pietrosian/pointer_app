'use strict';

const path = require('path');
const express = require('express');
const session = require('express-session');

const store = require('./store');
const { checkPassword, requireAuth } = require('./auth');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(
  session({
    secret: process.env.SESSION_SECRET || 'points-counter-dev-secret',
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true, maxAge: 1000 * 60 * 60 * 12 }, // 12h
  })
);

// --- Auth routes ---
app.post('/api/login', (req, res) => {
  const { password } = req.body || {};
  if (checkPassword(password)) {
    req.session.loggedIn = true;
    return res.json({ ok: true });
  }
  return res.status(401).json({ error: 'Wrong password' });
});

app.post('/api/logout', (req, res) => {
  req.session.destroy(() => res.json({ ok: true }));
});

app.get('/api/session', (req, res) => {
  res.json({ loggedIn: !!(req.session && req.session.loggedIn) });
});

// --- Student CRUD (all guarded) ---
app.get('/api/students', requireAuth, (req, res) => {
  res.json(store.getStudents());
});

app.post('/api/students', requireAuth, (req, res) => {
  const { name } = req.body || {};
  if (!name || !String(name).trim()) {
    return res.status(400).json({ error: 'Name is required' });
  }
  res.status(201).json(store.createStudent(name));
});

app.put('/api/students/:id', requireAuth, (req, res) => {
  const updated = store.updateStudent(req.params.id, req.body || {});
  if (!updated) return res.status(404).json({ error: 'Not found' });
  res.json(updated);
});

app.delete('/api/students/:id', requireAuth, (req, res) => {
  const ok = store.deleteStudent(req.params.id);
  if (!ok) return res.status(404).json({ error: 'Not found' });
  res.json({ ok: true });
});

// Commit session points to a student's overall total.
app.post('/api/students/:id/points', requireAuth, (req, res) => {
  const { delta } = req.body || {};
  const updated = store.addPoints(req.params.id, delta);
  if (!updated) return res.status(404).json({ error: 'Not found' });
  res.json(updated);
});

// --- Static frontend ---
app.use(express.static(path.join(__dirname, '..', 'public')));

app.listen(PORT, () => {
  console.log(`Points Counter running at http://localhost:${PORT}`);
});
