"""Routing engine tests: gates, ranking, fail-closed behavior, trace transparency."""

from ai.routing.engine import Candidate, RoutingConstraints, route


def candidate(
    model_key,
    provider_kind="mock",
    priority=100,
    input_cost=None,
    output_cost=None,
    capabilities=("chat",),
    latency_class="medium",
    enabled=True,
):
    return Candidate(
        model_key=model_key,
        provider_kind=provider_kind,
        display_name=model_key,
        capabilities=list(capabilities),
        priority=priority,
        latency_class=latency_class,
        input_cost_per_1m=input_cost,
        output_cost_per_1m=output_cost,
        enabled=enabled,
    )


def test_disabled_candidates_dropped():
    result = route([candidate("a", enabled=False)], RoutingConstraints())
    assert result.ok is False
    assert result.selected is None
    assert result.rejected == [{"model": "a", "reason": "disabled"}]
    assert "FAIL CLOSED" in result.explanation


def test_missing_capability_dropped():
    result = route(
        [candidate("text-only", capabilities=("chat",)), candidate("vision", capabilities=("chat", "vision"))],
        RoutingConstraints(capability="vision"),
    )
    assert result.ok is True
    assert result.selected.model_key == "vision"
    assert {"model": "text-only", "reason": "missing capability 'vision'"} in result.rejected


def test_fail_closed_when_capability_missing_everywhere():
    result = route([candidate("a")], RoutingConstraints(capability="vision"))
    assert result.ok is False
    assert "FAIL CLOSED" in result.explanation


def test_policy_exclusion_removes_model():
    result = route(
        [candidate("blocked", priority=1), candidate("safe", priority=99)],
        RoutingConstraints(exclude_models=["blocked"]),
    )
    assert result.selected.model_key == "safe"
    assert {"model": "blocked", "reason": "excluded by organization policy"} in result.rejected


def test_policy_exclusion_can_cause_fail_closed():
    result = route([candidate("only")], RoutingConstraints(exclude_models=["only"]))
    assert result.ok is False
    assert "FAIL CLOSED" in result.explanation


def test_lower_priority_wins():
    result = route([candidate("preferred", priority=1), candidate("backup", priority=99)], RoutingConstraints())
    assert result.selected.model_key == "preferred"


def test_cost_breaks_priority_tie():
    result = route(
        [candidate("expensive", priority=10, input_cost=10.0), candidate("cheap", priority=10, input_cost=0.1)],
        RoutingConstraints(),
    )
    assert result.selected.model_key == "cheap"


def test_model_key_breaks_full_tie():
    result = route([candidate("b", priority=5), candidate("a", priority=5)], RoutingConstraints())
    assert result.selected.model_key == "a"


def test_preferred_model_wins_over_priority():
    result = route(
        [candidate("pinned", priority=99), candidate("default", priority=1)],
        RoutingConstraints(preferred_model="pinned"),
    )
    assert result.selected.model_key == "pinned"


def test_preferred_model_still_gated_by_exclusion():
    result = route(
        [candidate("pinned", priority=99), candidate("default", priority=1)],
        RoutingConstraints(preferred_model="pinned", exclude_models=["pinned"]),
    )
    assert result.selected.model_key == "default"


def test_cost_ceiling_filters_when_cheaper_option_exists():
    result = route(
        [candidate("premium", input_cost=50.0), candidate("budget", input_cost=1.0)],
        RoutingConstraints(max_input_cost_per_1m=5.0),
    )
    assert result.selected.model_key == "budget"


def test_cost_ceiling_waived_when_nothing_affordable():
    # Availability beats silent failure: the ceiling is waived, ranking still applies.
    result = route(
        [candidate("costly-a", input_cost=50.0, priority=2), candidate("costly-b", input_cost=80.0, priority=1)],
        RoutingConstraints(max_input_cost_per_1m=1.0),
    )
    assert result.ok is True
    assert result.selected.model_key == "costly-b"
    assert any("waived" in t for t in result.trace)


def test_latency_constraint_filters():
    result = route(
        [candidate("slow", latency_class="slow"), candidate("fast", latency_class="fast")],
        RoutingConstraints(max_latency_class="fast"),
    )
    assert result.selected.model_key == "fast"


def test_latency_constraint_waived_when_nothing_within():
    result = route([candidate("only-slow", latency_class="slow")], RoutingConstraints(max_latency_class="fast"))
    assert result.ok is True
    assert result.selected.model_key == "only-slow"


def test_trace_is_human_readable():
    result = route([candidate("a"), candidate("b", priority=1)], RoutingConstraints())
    assert any("enabled" in t for t in result.trace)
    assert any("capability" in t.lower() for t in result.trace)
    assert any("Ranked by" in t for t in result.trace)


def test_rejection_reasons_are_recorded():
    result = route(
        [
            candidate("off", enabled=False),
            candidate("novision", capabilities=("chat",)),
            candidate("good", capabilities=("chat", "vision")),
        ],
        RoutingConstraints(capability="vision"),
    )
    reasons = {r["model"]: r["reason"] for r in result.rejected}
    assert reasons["off"] == "disabled"
    assert reasons["novision"] == "missing capability 'vision'"


def test_as_dict_is_json_ready():
    d = route([candidate("a")], RoutingConstraints()).as_dict()
    assert d["selected"] == "a"
    assert d["provider"] == "mock"
    assert isinstance(d["trace"], list)
    assert isinstance(d["rejected"], list)


def test_as_dict_fail_closed():
    d = route([], RoutingConstraints()).as_dict()
    assert d["selected"] is None
    assert d["provider"] is None


def test_blended_cost_weights_output_twice():
    # Same input cost; lower output cost wins (output weighted 2x).
    result = route(
        [candidate("chatty", priority=5, input_cost=1.0, output_cost=10.0), candidate("terse", priority=5, input_cost=1.0, output_cost=0.5)],
        RoutingConstraints(),
    )
    assert result.selected.model_key == "terse"


def test_none_constraints_defaults():
    result = route([candidate("a")])
    assert result.ok is True
