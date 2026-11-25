import sys


def test_provider_plugins_register_when_the_worker_module_is_imported() -> None:
    """LiveKit only allows plugin registration on the main thread; jobs run elsewhere.

    Regression: importing the Deepgram plugin inside the job entrypoint crashed every call.
    """
    import agent.main  # noqa: F401

    assert "livekit.plugins.deepgram" in sys.modules
