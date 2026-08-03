# Points Counter

A small pixel-art web app for teachers to award points to students during a
live classroom session. Start a session for one student, tap a few keys to hand
out coins, and the points are saved to that student's running total when you
stop.

## Features

- Password-protected teacher login (single shared password).
- Add, rename, and delete students. Data persists to a JSON file on disk.
- Live sessions with keyboard-driven point awards and coin/sound effects.
- Optional countdown timer you can set with natural input (`6:00`, `90`,
  `5 minutes`).

## Requirements

- [Node.js](https://nodejs.org/) 18 or newer
- npm (ships with Node)

## Setup

```bash
npm install
```

### Configuration

The app reads two optional environment variables:

| Variable           | Default                      | Purpose                              |
| ------------------ | ---------------------------- | ------------------------------------ |
| `TEACHER_PASSWORD` | `teacher`                    | Password required to log in.         |
| `SESSION_SECRET`   | `points-counter-dev-secret`  | Secret used to sign session cookies. |
| `PORT`             | `3000`                       | Port the server listens on.          |

There is a `.env` file in the repo, but the server does **not** load it
automatically (no `dotenv` dependency). Set the variables inline instead:

```bash
TEACHER_PASSWORD="your-password" SESSION_SECRET="a-long-random-string" npm start
```

## Running the app

```bash
npm start
```

Then open <http://localhost:3000> in your browser. You should see:

```
Points Counter running at http://localhost:3000
```

## Using the app

1. **Log in** — Enter the teacher password on the start screen.
2. **Manage students** — In the left panel, type a name and click **Add**. Each
   student shows their current total; you can rename or delete them from the
   list.
3. **Start a session** — In the right panel, pick the **Active student** and
   click **Start session**.
4. **Award points** during the session using the keyboard:

   | Key | Points     |
   | --- | ---------- |
   | `Z` | +1 coin    |
   | `X` | +5         |
   | `C` | +10        |

5. **(Optional) Timer** — Type a duration (e.g. `6:00`, `90`, `5 minutes`) and
   click **Set timer**. Use **Clear** to remove it.
6. **Stop session** — Click **Stop session**. The points earned this session are
   committed to the student's overall total and you return to the dashboard.

## Data storage

Student data is stored in `server/data/students.json`. The file is created
automatically on first run and updated atomically (write-to-temp then rename).
Points never drop below zero. To reset all data, stop the server and delete that
file.

## Project structure

```
.
├── package.json          # scripts and dependencies
├── server/
│   ├── server.js         # Express app, routes, static hosting
│   ├── auth.js           # password check + auth middleware
│   ├── store.js          # JSON-file-backed student store
│   └── data/
│       └── students.json # persisted student data (auto-created)
└── public/               # static frontend
    ├── index.html
    ├── css/styles.css
    └── js/               # api, audio, effects, timer, students, session, app
```

## API reference

All `/api/students*` routes require an authenticated session.

| Method   | Route                       | Description                                  |
| -------- | --------------------------- | -------------------------------------------- |
| `POST`   | `/api/login`                | Log in with `{ password }`.                  |
| `POST`   | `/api/logout`               | Destroy the session.                         |
| `GET`    | `/api/session`              | Check login state.                           |
| `GET`    | `/api/students`             | List all students.                           |
| `POST`   | `/api/students`             | Create a student `{ name }`.                 |
| `PUT`    | `/api/students/:id`         | Update `{ name, points }`.                   |
| `DELETE` | `/api/students/:id`         | Delete a student.                            |
| `POST`   | `/api/students/:id/points`  | Add `{ delta }` to a student's total.        |
```