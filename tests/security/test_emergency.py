from clinic.security.emergency import detect_emergency


def test_emergency_phrases_take_precedence() -> None:
    assert detect_emergency("I have severe chest pain")
    assert detect_emergency("I cannot breathe")
    assert detect_emergency("I think I took an overdose")
    assert not detect_emergency("I need a refill")
