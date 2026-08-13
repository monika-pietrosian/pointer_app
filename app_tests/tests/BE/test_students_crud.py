"""Student CRUD: /api/students and /api/students/:id[/points].

Parallel-safety rules for this file:

* Never assert on ``len(GET /api/students)``. Other workers add and remove
  students while you read. Assert that *your* id is present or absent instead.
* Never assert that a just-deleted id returns 404. ``store.nextId()`` is
  ``max(remaining) + 1``, so deleting the highest id frees it and a concurrent
  create can take it. For not-found cases use an id that was never issued
  (999999).
* Never assert an absolute id value, only that it is a positive int.
* Take students from the ``student`` fixture where you can -- it cleans up even
  when the test fails. Create inline only when the create *response*, or the
  student's absence at the end, is what the test is about.
* Do not wrap ``POST /api/students/:id/points`` in ``retry_async``: it is
  additive, so retrying a request that already landed adds the delta twice.
  Same for ``POST /api/students``, for a different reason: a retry after a
  landed create makes a second student whose id the test never learns, leaking a
  row into the store. GET/PUT/DELETE are idempotent and safe to wrap.
* Assert the status of a setup call, never ``if response.status_code == 201:``.
  A conditional body turns a broken setup into a *passing* test that checked
  nothing.

Parametrisation rules for this file:

* One case per row, and give every row an ``id``. Without ids pytest renders
  dicts as ``payload0``, ``payload1``, and a CI failure names nothing useful.
* Parametrise the *payload*, not a value inside it, whenever "field absent" is
  one of the cases -- ``{}`` and ``{"delta": None}`` are different requests, and
  a sentinel value only hides that.
* Each row gets its own ``student`` fixture instance, so the additive
  ``/points`` endpoint starts from 0 in every row. Rows cannot leak points into
  one another and can run on different xdist workers.
"""

from __future__ import annotations

import httpx
import pytest

from app_tests.exponential_backoff import retry_async

NEVER_ISSUED_ID = 999999


async def test_create_student_starts_at_zero_points(
    auth_client: httpx.AsyncClient, unique_name: str
) -> None:
    response = await auth_client.post("/api/students", json={"name": unique_name})

    assert response.status_code == 201, response.text
    body = response.json()

    try:
        assert body["name"] == unique_name
        assert body["points"] == 0
        assert isinstance(body["id"], int)
        assert body["id"] > 0
    finally:
        # Not the `student` fixture, because the response of the create call is
        # itself under test here. Clean up in finally so a failed assertion
        # still leaves the store tidy.
        await auth_client.delete(f"/api/students/{body['id']}")


# --- Create: negative cases ------------------------------------------------
#
# No `student` fixture and no cleanup: every row is expected to create nothing.
# If one starts returning 201 the assertion fails *and* leaks a row, which is
# the right trade -- speculative cleanup would hide the symptom.
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="name-absent"),
        pytest.param({"name": ""}, id="name-empty"),
        pytest.param({"name": "   "}, id="name-only-spaces"),
        pytest.param({"name": "\t\n"}, id="name-only-whitespace"),
        pytest.param({"name": None}, id="name-null"),
        # Falsy for a numeric reason: 0 fails `!name` before the trim runs, in
        # contrast to 123, which is accepted and stringified (see the TODO).
        pytest.param({"name": 0}, id="name-zero"),
    ],
)
async def test_create_student_rejects_a_blank_name(
    auth_client: httpx.AsyncClient, payload: dict
) -> None:
    response = await auth_client.post("/api/students", json=payload)

    assert response.status_code == 400, response.text
    assert response.json() == {"error": "Name is required"}


# --- Create: name trimming -------------------------------------------------
#
# Parametrised on a format string, not on the finished name: the name has to
# embed `unique_name`, which only exists once the test is running.
@pytest.mark.parametrize(
    "template",
    [
        pytest.param("  {name}  ", id="padded-both-sides"),
        pytest.param("{name}   ", id="trailing-spaces"),
        pytest.param("   {name}", id="leading-spaces"),
        pytest.param("\t{name}\n", id="surrounding-whitespace"),
    ],
)
async def test_create_student_trims_the_name(
    auth_client: httpx.AsyncClient, unique_name: str, template: str
) -> None:
    response = await auth_client.post(
        "/api/students", json={"name": template.format(name=unique_name)}
    )

    assert response.status_code == 201, response.text
    body = response.json()

    try:
        assert body["name"] == unique_name
    finally:
        await auth_client.delete(f"/api/students/{body['id']}")


async def test_the_student_list_contains_the_fixture_student(
    auth_client: httpx.AsyncClient, student: dict
) -> None:
    """Membership, never count -- other workers create and delete as we read."""
    response = await retry_async(lambda: auth_client.get("/api/students"))

    assert response.status_code == 200, response.text
    assert student["id"] in {s["id"] for s in response.json()}


# --- POST /:id/points: additive, with JS coercion --------------------------
#
# `expected` is the total after ONE call against a fresh student (points 0),
# which is why every row needs its own `student`.
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param({"delta": 5}, 5, id="int"),
        pytest.param({"delta": 10}, 10, id="int-larger"),
        # Number("5") is 5: a numeric string is accepted.
        pytest.param({"delta": "5"}, 5, id="numeric-string-coerced"),
        # Number("abc") is NaN and `NaN || 0` is 0, so a garbage delta is a
        # silent no-op with a 200 rather than a 400. Asserting the current
        # behaviour, not endorsing it.
        pytest.param({"delta": "abc"}, 0, id="garbage-string-is-a-no-op"),
        pytest.param({"delta": None}, 0, id="null-is-a-no-op"),
        pytest.param({}, 0, id="delta-absent-is-a-no-op"),
        # JSON true reaches Number(true) === 1. Current behaviour only.
        pytest.param({"delta": True}, 1, id="bool-true-counts-as-one"),
        # store.js addPoints floors at 0, so a negative delta against a
        # zero-point student cannot go below zero. Contrast with PUT, which does
        # not clamp.
        pytest.param({"delta": -1000}, 0, id="negative-int-clamps-to-zero"),
        pytest.param({"delta": "-100"}, 0, id="negative-string-clamps-to-zero"),
    ],
)
async def test_points_delta_coercion(
    auth_client: httpx.AsyncClient, student: dict, payload: dict, expected: int
) -> None:
    # Bare await, no retry_async: this endpoint is additive, so retrying a
    # request that already landed would apply the delta twice.
    response = await auth_client.post(f"/api/students/{student['id']}/points", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()

    # Read the points response, not the create response the `student` fixture
    # returned -- that one still says 0.
    assert body["points"] == expected
    assert body["id"] == student["id"]
    assert body["name"] == student["name"]


async def test_points_accumulate_across_calls(
    auth_client: httpx.AsyncClient, student: dict
) -> None:
    """Not parametrised on purpose: the sequence *is* the thing under test.

    Splitting these into rows would need state shared between them, which is
    what makes a parametrised suite order-dependent. A loop inside one test
    keeps the ordering explicit and the student private to it.
    """
    for delta, running_total in ((10, 10), ("5", 15), ("abc", 15), (-1000, 0)):
        response = await auth_client.post(
            f"/api/students/{student['id']}/points", json={"delta": delta}
        )
        assert response.status_code == 200, response.text
        assert response.json()["points"] == running_total, f"after delta={delta!r}"


# --- PUT: replaces, and does not clamp -------------------------------------
@pytest.mark.parametrize(
    ("payload", "expected_points"),
    [
        pytest.param({"points": 42}, 42, id="replaces-points"),
        pytest.param({"points": 0}, 0, id="replaces-with-zero"),
        # No floor on this path, unlike POST /points. The asymmetry is real:
        # store.js updateStudent has no clamp.
        pytest.param({"points": -5}, -5, id="negative-is-stored-as-is"),
        # `typeof fields.points === 'number'` is false for a string, so this is
        # dropped silently and the student keeps its 0.
        pytest.param({"points": "99"}, 0, id="numeric-string-is-ignored"),
        pytest.param({}, 0, id="empty-body-is-a-no-op"),
    ],
)
async def test_put_sets_points(
    auth_client: httpx.AsyncClient, student: dict, payload: dict, expected_points: int
) -> None:
    # PUT sets rather than increments, so it is idempotent and safe to wrap --
    # the opposite of the /points test above.
    response = await retry_async(
        lambda: auth_client.put(f"/api/students/{student['id']}", json=payload)
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["points"] == expected_points
    # A points-only PUT leaves the name alone.
    assert body["name"] == student["name"]


# --- 404s ------------------------------------------------------------------
#
# Two stacked @parametrize decorators, so the 3 verbs x 2 ids cross into 6 rows
# and the node id names both axes, e.g. [non-numeric-id-post-points].
@pytest.mark.parametrize(
    ("method", "path_suffix", "payload"),
    [
        pytest.param("PUT", "", {"name": "nobody"}, id="put"),
        pytest.param("DELETE", "", None, id="delete"),
        pytest.param("POST", "/points", {"delta": 1}, id="post-points"),
    ],
)
@pytest.mark.parametrize(
    "student_id",
    [
        # Never issued rather than "just deleted": deleting the highest id frees
        # it for reuse, so a deleted id can be alive again by the time we look.
        pytest.param(NEVER_ISSUED_ID, id="unissued-id"),
        # Number("abc") is NaN and `s.id === NaN` is false for every row, so a
        # non-numeric id takes the same not-found path.
        pytest.param("abc", id="non-numeric-id"),
    ],
)
async def test_unknown_student_is_404(
    auth_client: httpx.AsyncClient,
    method: str,
    path_suffix: str,
    payload: dict | None,
    student_id: object,
) -> None:
    url = f"/api/students/{student_id}{path_suffix}"

    # Safe to retry even the additive verb: there is no student to increment, so
    # a landed-then-retried request changes nothing either way.
    response = await retry_async(lambda: auth_client.request(method, url, json=payload))

    assert response.status_code == 404, response.text
    assert response.json() == {"error": "Not found"}


async def test_delete_reports_ok(auth_client: httpx.AsyncClient, unique_name: str) -> None:
    """Inline create, because the student must be gone when this test ends.

    With the `student` fixture, teardown would DELETE an id this test already
    removed. Harmless today, but it would mask a delete that silently failed.
    """
    created = await auth_client.post("/api/students", json={"name": unique_name})
    assert created.status_code == 201, created.text

    response = await auth_client.delete(f"/api/students/{created.json()['id']}")

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}


# TODO, in rough order of value:
#   - PUT {"name": "  Grace  "} -> trimmed, and points untouched
#   - POST /points with a float delta (2.5) -> points become 2.5; decide whether
#     non-integer points are a bug before pinning the behaviour in a test
#   - POST /api/students {"name": 123} -> 201 with the *string* "123";
#     same decide-then-assert
