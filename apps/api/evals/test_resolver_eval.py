"""§9: routing accuracy + unroutable-skill lint (kills dark capabilities)."""
from apps.api.evals.golden import ROUTING_CASES
from apps.api.resolver.resolver import lint_resolver
from apps.api.services.execution import resolve_task


def test_routing_accuracy(seeded, db, org_id):
    correct = 0
    for task, expected in ROUTING_CASES:
        routes = resolve_task(db, task, org_id)
        assert routes, f"no route for: {task}"
        top = routes[0]
        if top["slug"] == expected:
            correct += 1
    accuracy = correct / len(ROUTING_CASES)
    print(f"\nROUTING ACCURACY: {accuracy:.0%}")
    assert accuracy == 1.0


def test_route_has_reason_and_confidence(seeded, db, org_id):
    routes = resolve_task(db, "a customer is angry and wants their money back", org_id)
    top = routes[0]
    assert top["slug"] == "handle-refund"
    assert top["confidence"] > 0
    assert "similarity" in top["reason"]


def test_no_unroutable_skills(seeded, db, org_id):
    # The hard rule: every compiled skill must be routable.
    assert lint_resolver(db, org_id) == []
