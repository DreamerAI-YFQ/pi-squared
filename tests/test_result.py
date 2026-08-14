from pi_agent.harness.result import err, get_or_throw, get_or_undefined, is_err, is_ok, ok


def test_ok():
    r = ok(1)
    assert is_ok(r)
    assert not is_err(r)
    assert r.value == 1


def test_err():
    r = err("boom")
    assert is_err(r)
    assert not is_ok(r)
    assert r.error == "boom"


def test_get_or_throw_ok():
    assert get_or_throw(ok(42)) == 42


def test_get_or_throw_err_raises():
    try:
        get_or_throw(err("failed"))
        assert False, "应该抛异常"
    except RuntimeError as e:
        assert str(e) == "failed"


def test_get_or_undefined():
    assert get_or_undefined(ok(42)) == 42
    assert get_or_undefined(err("failed")) is None
