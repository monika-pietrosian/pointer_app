# Postman tests for the Points Counter API

- `points-counter.postman_collection.json` — 30 requests, 68 assertions
- `points-counter.postman_environment.json` — `baseUrl`, `password`, `studentName`

## Start the server

```bash
TEACHER_PASSWORD="Regierunk" npm start
```

The server does **not** read `.env` (no `dotenv` dependency), so a plain
`npm start` uses the default password `teacher`. Whichever you use, set the
`password` variable to match.

## Run in the Postman app

1. **Import** both JSON files.
2. Select the **Points Counter - local** environment.
3. Open the collection → **Run** → Run Points Counter API.

Auth is a signed session cookie (`connect.sid` via `express-session`), not a
bearer token. The `1. Auth / Login` request is what authenticates the run;
Postman's cookie jar replays the cookie on everything after it, so no manual
`Authorization` header is needed anywhere.

## Run headless

```bash
npx newman run app_tests/postman/points-counter.postman_collection.json \
  --env-var baseUrl=http://localhost:3000 \
  --env-var password=Regierunk
```

## Notes

- **Order matters.** The requests are stateful: `Create student` stores the new
  id in the `studentId` collection variable, and later requests assert on running
  point totals (`0 → 5 → 15 → 0 → 42`). Run the collection top to bottom rather
  than firing individual requests out of sequence.
- **Data is real, and newman cannot pick the file.** The store is whichever JSON
  file the *server* was started with, so start it against the test store first:
  `npm run start:test` (see RISKS.md). Under a plain `npm start` a run touches
  your actual student data in `server/data/students.json`. The collection creates
  and then deletes everything it makes, and unlike pytest it has no canary guard,
  so check the server's `Student data file:` boot line before running it.
- **Ids get recycled.** `store.nextId()` is `max(remaining) + 1`, so deleting the
  highest-id student frees that id for the next create. The
  `Delete student - already gone (404)` case is only reliable because this
  collection runs serially and nothing creates in between. Do not copy that
  pattern into a parallel suite — assert not-found against an id that was never
  issued (`999999`) instead.
- The first request clears the cookie jar for `baseUrl` so a leftover session
  can't mask the expected `401`s. If Postman blocks programmatic cookie access,
  allow the domain via the **Cookies** manager under the Send button.

## What's covered

| Group | Cases |
| --- | --- |
| 1. Auth | wrong password, non-string password, unauthenticated `/api/students`, successful login (cookie is `HttpOnly`), session state before/after |
| 2. Students CRUD | create, name trimming, missing/blank name, list + shape check, `+5`, non-numeric delta ignored, numeric-string delta accepted, clamp at zero, PUT name+points, PUT `points` as string ignored, partial PUT, empty-body PUT, delete, delete twice, list excludes deleted |
| 3. Unknown ids | `404` on PUT / points / DELETE for a missing id, and for a non-numeric id |
| 4. Logout | logout, session reports logged out, guarded route returns `401` again |

Two quirks worth knowing, both asserted above because they are the current
behavior rather than obvious intent:

- `POST /api/students/:id/points` accepts `"10"` (via `Number(delta)`) but
  silently ignores `"abc"` with a `200`. `PUT` is stricter — it requires a real
  JSON number and drops `"99"` without complaint.
- `PUT` **replaces** `points` and does not clamp negatives; only
  `POST /points` floors the total at `0`.
