from app.main import _friendly_ai_error

class MockAPIError(Exception):
    def __init__(self, status, code=None):
        super().__init__("DO_NOT_DISPLAY_SENSITIVE_ERROR_BODY")
        self.status_code = status
        self.code = code


def test_401():
    msg = _friendly_ai_error(MockAPIError(401))
    assert '401' in msg and 'OPENAI_API_KEY' in msg


def test_quota():
    msg = _friendly_ai_error(MockAPIError(429, 'insufficient_quota'))
    assert '결제/잔액' in msg


def test_model():
    assert 'OPENAI_MODEL' in _friendly_ai_error(MockAPIError(404))


def test_secrets_not_exposed():
    err = MockAPIError(400)
    err.body = {'code': 'invalid_model', 'text':'sk-SUPER-SECRET'}
    msg = _friendly_ai_error(err)
    assert 'sk-SUPER-SECRET' not in msg
    assert 'DO_NOT_DISPLAY_SENSITIVE_ERROR_BODY' not in msg
