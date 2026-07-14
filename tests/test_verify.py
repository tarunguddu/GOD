from god_agent.verify import Verifier


class FakeResult:
    def __init__(self, rc, out, err="", timed_out=False):
        self.returncode = rc
        self.stdout = out
        self.stderr = err
        self.timed_out = timed_out

    @property
    def ok(self):
        return self.returncode == 0 and not self.timed_out


class FakeShell:
    def __init__(self, result):
        self._result = result
        self.last_command = None

    def run(self, command, timeout=None, approved=False):
        self.last_command = command
        return self._result


def test_passing_pytest_parsed():
    shell = FakeShell(FakeResult(0, "==== 5 passed in 0.1s ===="))
    v = Verifier(shell).run("pytest")
    assert v.passed
    assert v.passed_count == 5
    assert "VERIFIED PASS" in v.as_claim()


def test_failing_pytest_parsed():
    shell = FakeShell(FakeResult(1, "2 failed, 3 passed in 0.2s"))
    v = Verifier(shell).run("pytest")
    assert not v.passed
    assert v.failed_count == 2
    assert "VERIFIED FAIL" in v.as_claim()


def test_vacuous_green_detected():
    # 0 passed, only skips, but exit 0 — must NOT be reported as verified.
    shell = FakeShell(FakeResult(0, "0 passed, 7 skipped"))
    v = Verifier(shell).run("pytest")
    assert not v.passed
    assert any("vacuous" in n.lower() for n in v.notes)


def test_timeout_is_unverified():
    shell = FakeShell(FakeResult(124, "", "Timed out", timed_out=True))
    v = Verifier(shell).run("pytest")
    assert not v.passed
    assert "UNVERIFIED" in v.as_claim()


def test_jest_counts():
    shell = FakeShell(FakeResult(0, "Tests: 4 passed, 4 total"))
    v = Verifier(shell).run("npm test")
    assert v.passed
    assert v.passed_count == 4
