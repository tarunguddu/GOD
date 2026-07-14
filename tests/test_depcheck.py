from god_agent.depcheck import DependencyChecker


def test_typosquat_detected_offline():
    checker = DependencyChecker(online=False)
    v = checker.check("reqeusts", "pypi")  # close to "requests"
    assert v.risk == "danger"
    assert v.typosquat_of == "requests"


def test_known_popular_is_ok_offline():
    checker = DependencyChecker(online=False)
    v = checker.check("requests", "pypi")
    # offline -> existence unverifiable, but no typosquat flag
    assert v.typosquat_of is None
    assert v.risk in ("unverified", "ok")


def test_unverified_when_offline():
    checker = DependencyChecker(online=False)
    v = checker.check("some-internal-pkg-xyz", "pypi")
    assert v.risk == "unverified"
    assert v.exists is None


def test_check_many():
    checker = DependencyChecker(online=False)
    verdicts = checker.check_many(["requests", "djangoo"], "pypi")
    assert len(verdicts) == 2
    assert any(v.risk == "danger" for v in verdicts)
