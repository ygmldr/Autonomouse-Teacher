from autoteacher_m0.experiments.paired import run_mock_pairs


def test_twenty_pairs_independent_sessions_reproducible_outputs():
    first, second = run_mock_pairs(), run_mock_pairs()
    assert len(first["pairs"]) == 20 and len(first["runs"]) == 40
    assert first["budget"]["pending"] == 0
    assert first["budget"]["requests"] == 40
    assert len({entry["record"]["run_id"] for entry in first["runs"]}) == 40
    assert len({entry["record"]["session_id"] for entry in first["runs"]}) == 40
    assert {entry["record"]["candidate_id"] for entry in first["runs"]} == {"teacher_v0", "teacher_v1"}
    assert [entry["record"]["text"] for entry in first["runs"]] == [entry["record"]["text"] for entry in second["runs"]]
    assert not ({entry["record"]["session_id"] for entry in first["runs"]}
                & {entry["record"]["session_id"] for entry in second["runs"]})
    assert all(pair["comparison_status"] == "COMPARABLE" for pair in first["pairs"])
    assert all(entry["evaluation"]["score"] == 1 for entry in first["runs"])
    assert all(entry["accounting"]["route_id"] == "mock" for entry in first["runs"])
    assert all(float(entry["accounting"]["cost_usd"]) > 0 for entry in first["runs"])
    assert all(entry["billable_cost_usd"] == "0" for entry in first["runs"])


def test_candidate_input_has_no_contract_labels_or_simulated_holdout_split():
    from autoteacher_m0.experiments.mock import TeachingMockRuntime
    captured = []
    instances = []
    class Spy(TeachingMockRuntime):
        def __init__(self):
            super().__init__()
            instances.append(self)
        def run(self, request):
            captured.append(request)
            return super().run(request)
    run_mock_pairs(runtime_factory=Spy)
    assert len(instances) == 40 and len({id(instance) for instance in instances}) == 40
    for request in captured:
        assert not hasattr(request, "expected_misconceptions")
        assert all(label not in request.prompt for label in (
            "expected_concepts", "expected_misconceptions", "relation_patterns",
            "simulated_holdout", "assumes_monotonicity", "late_widening"))
    # This verifies API input minimization, not hostile-code filesystem isolation.
