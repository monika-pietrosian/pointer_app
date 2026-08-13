'use strict';

const fs = require('fs');
const path = require('path');

// Which JSON file backs the store. Overridable so a test run can point at its
// own file instead of the teacher's real data -- see RISKS.md for what this
// does and does not protect.
//
// Resolved once, at require time: changing POINTS_DATA_FILE while the process
// is running has no effect. A relative value is resolved against the process
// cwd, not against server/, so prefer an absolute path.
const DEFAULT_DATA_FILE = path.join(__dirname, 'data', 'students.json');
const DATA_FILE = process.env.POINTS_DATA_FILE
  ? path.resolve(process.env.POINTS_DATA_FILE)
  : DEFAULT_DATA_FILE;
const DATA_DIR = path.dirname(DATA_FILE);
const TMP_FILE = `${DATA_FILE}.tmp`;

function ensureFile() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(DATA_FILE)) {
    fs.writeFileSync(DATA_FILE, '[]', 'utf8');
  }
}

function readAll() {
  ensureFile();
  try {
    const raw = fs.readFileSync(DATA_FILE, 'utf8');
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    // Corrupt file: start fresh rather than crash.
    return [];
  }
}

// Atomic write: write to temp file then rename over the real file.
function writeAll(students) {
  ensureFile();
  fs.writeFileSync(TMP_FILE, JSON.stringify(students, null, 2), 'utf8');
  fs.renameSync(TMP_FILE, DATA_FILE);
}

function nextId(students) {
  return students.reduce((max, s) => Math.max(max, s.id), 0) + 1;
}

function getStudents() {
  return readAll();
}

function getStudent(id) {
  return readAll().find((s) => s.id === Number(id)) || null;
}

function createStudent(name) {
  const students = readAll();
  const student = { id: nextId(students), name: String(name).trim(), points: 0 };
  students.push(student);
  writeAll(students);
  return student;
}

function updateStudent(id, fields) {
  const students = readAll();
  const student = students.find((s) => s.id === Number(id));
  if (!student) return null;
  if (typeof fields.name === 'string') student.name = fields.name.trim();
  if (typeof fields.points === 'number') student.points = fields.points;
  writeAll(students);
  return student;
}

function deleteStudent(id) {
  const students = readAll();
  const idx = students.findIndex((s) => s.id === Number(id));
  if (idx === -1) return false;
  students.splice(idx, 1);
  writeAll(students);
  return true;
}

function addPoints(id, delta) {
  const students = readAll();
  const student = students.find((s) => s.id === Number(id));
  if (!student) return null;
  student.points += Number(delta) || 0;
  if (student.points < 0) student.points = 0;
  writeAll(students);
  return student;
}

module.exports = {
  // Exposed so the boot log can state which file this process will write to.
  // Not served over HTTP: the path is a local filesystem detail.
  dataFile: DATA_FILE,
  getStudents,
  getStudent,
  createStudent,
  updateStudent,
  deleteStudent,
  addPoints,
};
