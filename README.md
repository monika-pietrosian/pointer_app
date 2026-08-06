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

## Testing

The API test suite lives in `app_tests/` and is written with pytest + httpx. It
tests the running HTTP API rather than importing the Node code, so **the server
must already be running** before you invoke pytest — the suite does not start
one for you.

### Requirements

- Python 3.12 or newer (CI uses 3.12)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app_tests/requirements.txt
```

### Running the tests

Start the server in one terminal:

```bash
npm start
```

Then, from the repo root, in another terminal:

```bash
pytest
```

`pytest.ini` already points at `app_tests/tests`, puts the repo root on
`sys.path`, and enables `asyncio_mode = auto`, so no extra flags are needed. Run
in parallel with:

```bash
pytest -n auto --dist load
```

A session-scoped fixture polls `/api/session` with exponential backoff before
the first test, so starting the server a moment earlier is enough — no manual
wait loop required. If nothing is listening, the suite fails fast with a message
telling you to start the server.

### Configuration

| Variable           | Default                 | Purpose                                        |
| ------------------ | ----------------------- | ---------------------------------------------- |
| `POINTS_API_URL`   | `http://127.0.0.1:3000` | Base URL the tests hit.                        |
| `TEACHER_PASSWORD` | `teacher`               | Must match the password the server started with. |

If you started the server with a custom password, pass the same one to pytest:

```bash
POINTS_API_URL=http://127.0.0.1:3000 TEACHER_PASSWORD="your-password" pytest
```

> **The tests write to real data.** They run against
> `server/data/students.json`. Each test creates a uniquely-named student and
> deletes it at teardown, but back the file up first if it holds data you care
> about.

### In CI

`.github/workflows/api-tests.yml` runs the same suite on every push to `main`
and on pull requests: `npm ci`, install `app_tests/requirements.txt`, start
`node server/server.js` in the background, then
`pytest -n auto --dist load --junitxml=pytest-report.xml`. The JUnit report is
uploaded as the `pytest-report` artifact.

### Postman collection

There is also a Postman/newman collection covering the same API in
`app_tests/postman/` — see `app_tests/postman/README.md` for how to run it.

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
├── public/               # static frontend
│   ├── index.html
│   ├── css/styles.css
│   └── js/               # api, audio, effects, timer, students, session, app
├── pytest.ini            # pytest config (testpaths, asyncio mode)
└── app_tests/            # API tests
    ├── conftest.py       # shared fixtures (base_url, auth_client, student)
    ├── requirements.txt  # httpx, pytest, pytest-asyncio, pytest-xdist
    ├── tests/            # pytest test modules
    └── postman/          # Postman collection + newman instructions
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