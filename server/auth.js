'use strict';

// Single shared teacher password. Override in production with TEACHER_PASSWORD.
const TEACHER_PASSWORD = process.env.TEACHER_PASSWORD || 'teacher';

function checkPassword(password) {
  return typeof password === 'string' && password === TEACHER_PASSWORD;
}

// Guards /api routes: rejects requests without an authenticated session.
function requireAuth(req, res, next) {
  if (req.session && req.session.loggedIn) {
    return next();
  }
  return res.status(401).json({ error: 'Not authenticated' });
}

module.exports = { checkPassword, requireAuth };
