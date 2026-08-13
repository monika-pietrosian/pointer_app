# RISKS.md — splitting the test store out of `server/data/students.json`

## What changed

Before, `server/store.js` hardcoded one file. The API suite, the Playwright
suite, and the Postman collection all ran against the same
`server/data/students.json` the teacher's real classroom data lives in. The
evidence it was a real problem, not a theoretical one: at the time of this
change the working tree had three leftover `Ada Lovelace` rows (ids 3–5) in that
file from earlier test and Postman runs.

After:

| Piece | Change |
| --- | --- |
| `server/store.js` | Data file path comes from `POINTS_DATA_FILE`, falling back to the old default. Resolved once at require time. |
| `server/server.js` | Boot log prints the resolved path. |
| `app_tests/data/students.test.json` | The test store. Gitignored; the server creates it if missing. |
| `package.json` | `npm run start:test` = `npm start` with `POINTS_DATA_FILE` pointed at the test store. |
| `.github/workflows/api-tests.yml` | Sets `POINTS_DATA_FILE` for the job. |
| `app_tests/conftest.py` | `real_data_file_is_untouched` session fixture — canary check, described below. |

Blast radius: every write path in the app, since `store.js` backs all of
`/api/students*`. The change is a path computation, not a logic change, and the
default is byte-identical to the old constant — but "the app still writes
students" is now conditional on an environment variable that was not there
before.

## The core risk this introduces

**The configuration lives on the server process, and the tests are a different
process.**

`conftest.py` documents that the suite deliberately does not spawn a server
(under `pytest -n auto` every xdist worker would race for port 3000). So pytest
has no way to *set* `POINTS_DATA_FILE` for the thing it is testing. Setting it in
the pytest environment does nothing at all. The server read its environment at
boot, minutes earlier, in another terminal.

That converts an obvious, loud problem ("tests write to my real data, always")
into a quiet, conditional one ("tests write to my real data whenever someone
typed `npm start` instead of `npm run start:test`") — and the failure is
invisible, because the suite passes either way. Silent-and-occasional is worse to
live with than loud-and-always, which is why the mitigation below is part of the
change rather than a follow-up.

### Mitigation: the canary fixture, and exactly what it proves

`real_data_file_is_untouched` runs once per session, before any test:

1. Log in, create one student with a `pytest-canary-<uuid>` name.
2. Read `server/data/students.json` off disk and look for that name.
3. Delete the canary either way; fail the session with a fix-it message if it
   landed in the real file.

What it proves: the running server is not writing to the real store.

What it does **not** prove, in the order these are likely to bite:

- **It is not a proof of correct configuration.** A server pointed at some third
  file — a typo'd path, a stale test store, `/tmp` — passes. The assertion is
  "not the real store", nothing more.
- **It is a local-filesystem check.** If `POINTS_API_URL` points at another
  machine, the local path is meaningless, so the guard warns and continues. It
  does not skip: skipping in a session-scoped autouse fixture would skip the
  whole suite, turning "cannot verify" into "nothing ran", which is a worse
  outcome than an unguarded run you were told about.
- **It costs one real write when it fires.** Detection happens by doing the
  dangerous thing once, on purpose. Under `-n auto` that is one canary per xdist
  worker, so a forgotten `start:test` writes and deletes N rows in the real file
  before failing. Cheap next to the hundreds the full suite would write, but not
  zero, and a crash between create and delete leaks a row.
- **`REAL_DATA_FILE` in `conftest.py` duplicates `DEFAULT_DATA_FILE` in
  `store.js`.** Two languages, no shared source of truth. Move the real store and
  the guard goes stale *and still passes* — a green run then means nothing. This
  is the weakest joint in the change.
- **Postman/newman has no equivalent guard.** It hits the same server and
  inherits whatever file that server chose, with nothing checking. Same for
  anyone poking the API by hand.

## Other risks, roughly by likelihood

**Relative-path resolution.** `POINTS_DATA_FILE` is `path.resolve`d against
`process.cwd()`, not against `server/`. `npm run start:test` and the CI job both
happen to run from the repo root, so `app_tests/data/students.test.json` lands
where intended. Start the server from anywhere else with a relative override and
`store.js` will silently `mkdirSync` a fresh empty store in that directory — no
error, just a suite that suddenly sees no students and a stray directory on disk.
Absolute paths avoid this.

**A gitignored file that CI depends on.** `app_tests/data/students.test.json` is
not committed; `store.js`'s `ensureFile()` recreates it. That works today. It
also means the test store's existence depends on a side effect of the first write
path that touches it — if `ensureFile` is ever narrowed or the path becomes
non-writable (read-only mount, container user without permission), the failure
surfaces as odd 500s from `/api/students` rather than as a clear startup error.
The server never validates that its data file is writable at boot.

**Two files that drift.** The real store carries the teacher's actual roster; the
test store starts empty. Any test that quietly depended on the real file's
contents (fixed ids, "Artur" existing) would have broken here. The current suite
does not — `conftest.py` and `test_students_crud.py` both forbid asserting on
counts or absolute ids — so this is a constraint to keep holding, not a bug
today. New tests written against the empty test store may be *accidentally*
correct in a way they would not be against a populated one.

**Env var not covered by tests.** Nothing exercises `POINTS_DATA_FILE` itself.
There is no test that the default is unchanged, that an override is honoured, or
that a relative path resolves against cwd — the resolution logic is trusted
because it is short. The suite passing is not evidence the override works; the
only evidence is the boot log and the canary fixture.

**`npm run start:test` is bash-only.** `VAR=value node ...` does not work in
`cmd.exe`. Windows contributors have to set the variable themselves. Not a
problem for this repo's linux/macOS instructions, but the script will look broken
to anyone on Windows.

**Read-modify-write races are unchanged, and now concentrated.** `store.js` does
`readAll()` → mutate → `writeAll()` with no locking, so two concurrent requests
can lose one another's write. `pytest -n auto` is the heaviest concurrent load
this app ever sees, and all of it now lands on one file. Pre-existing, not caused
by this change, and a plausible source of rare flakes that will look like test
bugs rather than store bugs.

## Adjacent findings, not fixed here

- `server/data/students.json` in the working tree still holds the three leftover
  `Ada Lovelace` rows from earlier runs. This change stops new pollution; it does
  not clean up the old rows. Deciding which of ids 3–5 are real students is a
  human call — `git checkout server/data/students.json` would drop id 5 and keep
  3 and 4, which may or may not be right.
- The real `TEACHER_PASSWORD` from `.env` is committed in
  `app_tests/postman/README.md` and both Postman JSON files. Unrelated to the
  store split, but it is a live secret in git history and rotating it is a
  separate decision.
- `app_tests/__pycache__/*.pyc` and `app_tests/tests/__pycache__/*.pyc` are
  tracked in git. The new `.gitignore` does not untrack them; `git rm --cached`
  is a separate, deliberate step.

## What would make this safe to rely on

1. One source of truth for the default path, so the guard cannot go stale — e.g.
   have `store.js` fail fast when `POINTS_DATA_FILE` is unset *and*
   `NODE_ENV=test`, or read the boot log's `Student data file:` line in CI and
   assert on it.
2. A test for the override itself: boot the server with `POINTS_DATA_FILE`
   pointing at a temp file, create a student, assert it appears there and that
   `server/data/students.json` is byte-identical before and after.
3. A CI assertion that `git diff --exit-code server/data/students.json` is clean
   after the test step. That catches the whole class of problem from the outside,
   independent of how the guard is wired.
