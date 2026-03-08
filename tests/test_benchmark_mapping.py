from leaksentinel.eval.benchmark import expected_decision_from_label


def test_expected_decision_mapping() -> None:
    assert expected_decision_from_label("leak") == "LEAK_CONFIRMED"
    assert expected_decision_from_label("planned_ops") == "IGNORE_PLANNED_OPS"
    assert expected_decision_from_label("normal") == "INVESTIGATE"
    assert expected_decision_from_label("investigate") is None

