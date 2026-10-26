"""Policy engine tests: condition evaluation, scope, precedence, malformed rules."""

from ai.guardrails.policy_engine import (
    EvaluationContext,
    PolicyRule,
    effective_action,
    evaluate_policies,
)


def rule(action="block", **kw):
    return PolicyRule(
        id=kw.pop("id", "p1"),
        name=kw.pop("name", "test policy"),
        enabled=kw.pop("enabled", True),
        severity=kw.pop("severity", "high"),
        action=action,
        scope=kw.pop("scope", "organization"),
        scope_role=kw.pop("scope_role", None),
        project_id=kw.pop("project_id", None),
        conditions=kw.pop("conditions", [{"field": "prompt_contains", "op": "contains", "value": "secret"}]),
    )


def action_of(rules, ctx):
    decisions = evaluate_policies(rules, ctx)
    action, triggering = effective_action(decisions)
    return action, triggering


def test_no_rules_allows():
    assert action_of([], EvaluationContext(prompt="hi")) == ("allow", None)


def test_disabled_rule_ignored():
    r = rule(action="block", enabled=False)
    assert action_of([r], EvaluationContext(prompt="my secret")) == ("allow", None)


def test_invalid_action_ignored():
    r = rule(action="explode")
    assert action_of([r], EvaluationContext(prompt="my secret")) == ("allow", None)


def test_block_matches_when_condition_holds():
    r = rule(action="block")
    action, triggering = action_of([r], EvaluationContext(prompt="the secret is out"))
    assert action == "block"
    assert triggering is not None
    assert triggering.policy_name == "test policy"


def test_no_match_allows():
    r = rule(action="block")
    assert action_of([r], EvaluationContext(prompt="innocent question")) == ("allow", None)


def test_contains_is_case_insensitive():
    r = rule(action="warn")
    assert action_of([r], EvaluationContext(prompt="SECRET sauce"))[0] == "warn"


def test_block_beats_warn():
    rules = [
        rule(action="warn", id="w", name="warn rule"),
        rule(action="block", id="b", name="block rule"),
    ]
    action, triggering = action_of(rules, EvaluationContext(prompt="my secret"))
    assert action == "block"
    assert triggering.policy_id == "b"


def test_mask_beats_warn():
    rules = [
        rule(action="warn", id="w"),
        rule(action="mask", id="m", conditions=[{"field": "pii_type", "op": "in", "value": ["email"]}]),
    ]
    action, triggering = action_of(rules, EvaluationContext(prompt="x", pii_types=["email"]))
    assert action == "mask"
    assert triggering.policy_id == "m"


def test_allow_rule_does_not_suppress_block():
    rules = [
        rule(action="allow", id="a", name="allow rule"),
        rule(action="block", id="b", name="block rule"),
    ]
    assert action_of(rules, EvaluationContext(prompt="my secret"))[0] == "block"


def test_multiple_conditions_all_must_match():
    r = rule(
        action="block",
        conditions=[
            {"field": "prompt_contains", "op": "contains", "value": "secret"},
            {"field": "model", "op": "equals", "value": "gpt-4o"},
        ],
    )
    assert action_of([r], EvaluationContext(prompt="my secret", model="gpt-4o-mini"))[0] == "allow"
    assert action_of([r], EvaluationContext(prompt="my secret", model="gpt-4o"))[0] == "block"


def test_injection_category_in():
    r = rule(
        action="block",
        conditions=[{"field": "prompt_injection_category", "op": "in", "value": ["instruction_override"]}],
    )
    assert action_of([r], EvaluationContext(injection_categories=["instruction_override"]))[0] == "block"
    assert action_of([r], EvaluationContext(injection_categories=["other"]))[0] == "allow"


def test_injection_score_threshold():
    r = rule(
        action="block",
        conditions=[{"field": "injection_score", "op": "gte", "value": 3}],
    )
    assert action_of([r], EvaluationContext(injection_score=5))[0] == "block"
    assert action_of([r], EvaluationContext(injection_score=1))[0] == "allow"


def test_prompt_length_over():
    r = rule(
        action="warn",
        conditions=[{"field": "prompt_length_over", "op": "gt", "value": 100}],
    )
    assert action_of([r], EvaluationContext(prompt="x" * 200))[0] == "warn"
    assert action_of([r], EvaluationContext(prompt="short"))[0] == "allow"


def test_response_contains_for_output_policies():
    r = rule(
        action="block",
        conditions=[{"field": "response_contains", "op": "matches", "value": "api[_ ]?key"}],
    )
    assert action_of([r], EvaluationContext(response="your api_key is 123"))[0] == "block"
    assert action_of([r], EvaluationContext(response="all clear"))[0] == "allow"


def test_invalid_regex_fails_closed_to_no_match():
    r = rule(action="block", conditions=[{"field": "prompt_contains", "op": "matches", "value": "([unclosed"}])
    assert action_of([r], EvaluationContext(prompt="anything"))[0] == "allow"


def test_project_scope():
    r = rule(action="block", scope="project", project_id="proj-1")
    assert action_of([r], EvaluationContext(prompt="my secret", project_id="proj-1"))[0] == "block"
    assert action_of([r], EvaluationContext(prompt="my secret", project_id="proj-2"))[0] == "allow"


def test_role_scope():
    r = rule(action="block", scope="role", scope_role="viewer")
    assert action_of([r], EvaluationContext(prompt="my secret", actor_role="viewer"))[0] == "block"
    assert action_of([r], EvaluationContext(prompt="my secret", actor_role="owner"))[0] == "allow"


def test_unconditional_policy_always_applies():
    r = rule(action="warn", conditions=[])
    assert action_of([r], EvaluationContext(prompt="literally anything"))[0] == "warn"


def test_matched_conditions_are_reported():
    r = rule(action="block")
    decisions = evaluate_policies([r], EvaluationContext(prompt="the secret is out"))
    assert decisions[0].matched is True
    assert len(decisions[0].matched_conditions) == 1
    assert decisions[0].matched_conditions[0]["matched"] is True
    assert "block" in decisions[0].explanation


def test_long_prompt_truncated_in_report():
    r = rule(action="warn", conditions=[{"field": "prompt_contains", "op": "contains", "value": "needle"}])
    decisions = evaluate_policies([r], EvaluationContext(prompt="needle " + "x" * 1000))
    actual = decisions[0].matched_conditions[0]["actual"]
    assert len(actual) <= 310


def test_from_model_reads_db_row_fields():
    class M:
        id = "7"
        name = "db policy"
        enabled = True
        severity = "medium"
        action = "warn"
        scope = "organization"
        scope_role = None
        project_id = None
        version = 3
        conditions = [{"field": "model", "op": "equals", "value": "x"}]

    parsed = PolicyRule.from_model(M())
    assert parsed.id == "7"
    assert parsed.action == "warn"
    assert parsed.conditions == [{"field": "model", "op": "equals", "value": "x"}]


def test_from_model_tolerates_none_conditions():
    class M:
        id = "8"
        name = "no conditions"
        enabled = True
        severity = "low"
        action = "allow"
        scope = "organization"
        scope_role = None
        project_id = None
        version = 1
        conditions = None

    parsed = PolicyRule.from_model(M())
    assert parsed.conditions == []
