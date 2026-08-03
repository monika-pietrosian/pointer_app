'use strict';

// Thin fetch wrappers around the backend API. All return parsed JSON
// and throw on non-2xx so callers can try/catch.
const api = (() => {
  async function req(method, url, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* empty body */
    }
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  return {
    login: (password) => req('POST', '/api/login', { password }),
    logout: () => req('POST', '/api/logout'),
    checkSession: () => req('GET', '/api/session'),
    listStudents: () => req('GET', '/api/students'),
    createStudent: (name) => req('POST', '/api/students', { name }),
    updateStudent: (id, fields) => req('PUT', `/api/students/${id}`, fields),
    deleteStudent: (id) => req('DELETE', `/api/students/${id}`),
    addPoints: (id, delta) => req('POST', `/api/students/${id}/points`, { delta }),
  };
})();
