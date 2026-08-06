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
  when the test fails.
* Do not wrap ``POST /api/students/:id/points`` in ``retry_async``: it is
  additive, so retrying a request that already landed adds the delta twice.
"""

from __future__ import annotations

import httpx


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


# TODO, in rough order of value:
#   - name is trimmed: "  Grace  " -> "Grace"
#   - missing name ({}) and blank name ({"name": "   "}) -> 400 Name is required
#   - GET /api/students contains the `student` fixture's id (membership, not count)
#   - POST /points with delta 5 -> points 5
#   - POST /points with delta "10" -> points 15  (Number("10") coerces)
#   - POST /points with delta "abc" -> 200, points unchanged (Number(x) || 0)
#   - POST /points with delta -1000 -> points clamp to 0, never negative
#   - PUT {"name", "points"} -> replaces points (contrast with additive /points)
#   - PUT {"points": "99"} -> ignored, needs a real JSON number
#   - PUT {"name": only} -> points untouched;  PUT {} -> no-op
#   - PUT with a negative points value is stored as-is: PUT does not clamp
#   - DELETE -> {"ok": true}, then the id is gone from the list
#   - 404 on PUT / POST /points / DELETE for id 999999 and for id "abc"
#     (Number("abc") is NaN, which matches nothing)
