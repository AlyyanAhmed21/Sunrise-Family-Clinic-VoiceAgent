import pytest

from clinic.security.emergency import detect_emergency


def test_emergency_phrases_take_precedence() -> None:
    assert detect_emergency("I have severe chest pain")
    assert detect_emergency("I cannot breathe")
    assert detect_emergency("I think I took an overdose")
    assert not detect_emergency("I need a refill")


def test_emergency_detector_covers_breathing_and_explicit_emergency() -> None:
    assert detect_emergency("I am having difficulty breathing")
    assert detect_emergency("I have shortness of breath")
    assert detect_emergency("This is an emergency")
    assert not detect_emergency("I would like an appointment")


def test_explicit_suicidal_phrases_take_precedence() -> None:
    assert detect_emergency("I want to kill myself")
    assert detect_emergency("I want to die")


@pytest.mark.parametrize(
    "said",
    [
        # Regression from a live call: these reached the LLM instead of the scripted 911 path.
        "Hi. Hello. I need some help. I'm having really bad pain in my chest.",
        "I'm having difficulty to breathe as well.",
        # Other natural phrasings
        "my chest feels really tight",
        "there's a lot of pressure on my chest",
        "I'm struggling to breathe",
        "it's hard to breathe",
        "my dad passed out and won't wake up",
        "her face is drooping and she has slurred speech",
        "my son swallowed something, I think it's poisoning",
        "my throat is swelling after a bee sting",
        "I've been thinking about ending it, I want to end my life",
        "the cut won't stop bleeding",
    ],
)
def test_natural_emergency_phrasings_are_detected(said: str) -> None:
    assert detect_emergency(said)


@pytest.mark.parametrize(
    "said",
    [
        "I have a question about my chest x-ray bill",
        "I need a refill for my breathing inhaler",
        "I'd like to book a check-up for my poison ivy rash",
        "I've had a headache for a few days",
        "I'm not short of breath, I just need my lab status",
        "Can I schedule a follow-up about my blood pressure?",
    ],
)
def test_routine_requests_do_not_trigger(said: str) -> None:
    assert not detect_emergency(said)


def test_negated_emergency_phrases_do_not_trigger() -> None:
    assert not detect_emergency("I do not have chest pain")
    assert not detect_emergency("I am not having difficulty breathing")
    assert not detect_emergency("This is not an emergency")
    assert detect_emergency("I do not have chest pain, but I cannot breathe")
