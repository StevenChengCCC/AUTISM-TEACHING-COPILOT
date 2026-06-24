from app.main import health_check


def test_health_endpoint_does_not_return_api_keys():
    payload = health_check()
    text = repr(payload)
    assert "OPENAI_API_KEY" not in text
    assert "AZURE_OPENAI_API_KEY" not in text
    assert "PEXELS_API_KEY" not in text
    assert "PIXABAY_API_KEY" not in text
