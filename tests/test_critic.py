from god_agent.reasoning.critic import SelfCritic, Severity


def test_clean_code_no_findings():
    code = "def add(a, b):\n    return a + b\n"
    c = SelfCritic().review(code, "m.py")
    assert c.syntax_ok
    assert not c.blocking
    assert c.max_severity == Severity.INFO


def test_syntax_error_blocks():
    c = SelfCritic().review("def broken(:\n", "m.py")
    assert not c.syntax_ok
    assert c.blocking


def test_detects_aws_key():
    code = 'KEY = "AKIA1234567890ABCDEF"\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule.startswith("secret:") for f in c.findings)
    assert c.blocking


def test_secret_value_is_redacted():
    code = 'password = "supersecret123"\n'
    c = SelfCritic().review(code, "m.py")
    secret_findings = [f for f in c.findings if f.rule.startswith("secret:")]
    assert secret_findings
    assert "supersecret123" not in secret_findings[0].snippet
    assert "REDACTED" in secret_findings[0].snippet


def test_placeholder_secret_ignored():
    code = 'api_key = "your-api-key-here"\n'
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule.startswith("secret:") for f in c.findings)


def test_env_var_not_flagged():
    code = 'token = os.environ["TOKEN"]\n'
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule.startswith("secret:") for f in c.findings)


def test_detects_eval():
    c = SelfCritic().review("def f(x):\n    return eval(x)\n", "m.py")
    assert any(f.rule == "vuln:dynamic-exec" for f in c.findings)
    assert c.blocking


def test_detects_shell_injection():
    code = "import subprocess\nsubprocess.run(cmd, shell=True)\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "vuln:shell-injection" for f in c.findings)


def test_detects_sql_injection():
    code = (
        "def q(cur, name):\n"
        "    cur.execute('SELECT * FROM t WHERE n = ' + name)\n"
    )
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "vuln:sql-injection" for f in c.findings)


def test_detects_stub_function():
    code = "def todo():\n    pass\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "stub:empty-function" for f in c.findings)


def test_detects_not_implemented_stub():
    code = "def todo():\n    raise NotImplementedError\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "stub:empty-function" for f in c.findings)


def test_docstring_only_function_is_stub():
    code = 'def todo():\n    """does nothing yet"""\n    ...\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "stub:empty-function" for f in c.findings)


def test_real_function_with_docstring_not_stub():
    code = 'def real():\n    """adds"""\n    return 1 + 1\n'
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "stub:empty-function" for f in c.findings)


def test_bare_except_is_low():
    code = "def f():\n    try:\n        pass\n    except:\n        pass\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "smell:bare-except" for f in c.findings)


def test_placeholder_bypass_is_closed():
    # A real secret with a benign comment on the same line must STILL be flagged
    # (the old line-scoped placeholder check let this through).
    code = 'KEY = "AKIA1234567890ABCDEF"  # example\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule.startswith("secret:") for f in c.findings)
    assert c.blocking


def test_unquoted_secret_is_redacted():
    code = "KEY = AKIA1234567890ABCDEF\n"
    c = SelfCritic().review(code, "m.py")
    secret = [f for f in c.findings if f.rule.startswith("secret:")]
    assert secret
    assert "AKIA1234567890ABCDEF" not in secret[0].snippet


def test_shell_true_with_nested_call_detected():
    # Regex-based detection used to miss a nested call before the kwarg.
    code = ("import subprocess, shlex\n"
            "subprocess.Popen(shlex.split(cmd), shell=True)\n")
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "vuln:shell-injection" for f in c.findings)


def test_pyw_extension_still_runs_ast_checks():
    code = "def f(x):\n    return eval(x)\n"
    c = SelfCritic().review(code, "evil.pyw")
    assert any(f.rule == "vuln:dynamic-exec" for f in c.findings)


def test_pickle_is_blocking():
    code = "import pickle\ndef load(b):\n    return pickle.loads(b)\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "vuln:pickle-loads" for f in c.findings)
    assert c.blocking          # deserialisation now blocks (was MEDIUM/non-blocking)


def test_url_embedded_credential_detected():
    code = 'DB = "postgres://admin:hunter2pass@db.example.com/app"\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "secret:url-embedded-credential" for f in c.findings)


def test_google_api_key_detected():
    code = 'K = "AIzaSyA1234567890abcdefghijklmnopqrstuv"\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "secret:google-api-key" for f in c.findings)


def test_re_compile_not_flagged_as_dynamic_exec():
    # re.compile() is benign and must NOT trip the eval/exec/compile check.
    code = "import re\nPAT = re.compile(r'abc')\n"
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "vuln:dynamic-exec" for f in c.findings)


def test_builtin_compile_is_flagged():
    code = "def f(s):\n    return compile(s, '<s>', 'exec')\n"
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule == "vuln:dynamic-exec" for f in c.findings)


def test_inline_suppression_named_rule():
    code = "import subprocess\nsubprocess.run(c, shell=True)  # god:allow shell-injection\n"
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "vuln:shell-injection" for f in c.findings)


def test_blanket_suppression_does_not_hide_secrets():
    # A blanket `# god:allow` must NEVER suppress a secret finding.
    code = 'KEY = "AKIA1234567890ABCDEF"  # god:allow\n'
    c = SelfCritic().review(code, "m.py")
    assert any(f.rule.startswith("secret:") for f in c.findings)


def test_explicit_secret_suppression_works():
    code = 'KEY = "AKIA1234567890ABCDEF"  # god:allow secret:aws-access-key\n'
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "secret:aws-access-key" for f in c.findings)


def test_abstractmethod_not_flagged_as_stub():
    code = (
        "from abc import abstractmethod\n"
        "class Base:\n"
        "    @abstractmethod\n"
        "    def do(self):\n"
        "        ...\n"
    )
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "stub:empty-function" for f in c.findings)


def test_overload_not_flagged_as_stub():
    code = (
        "from typing import overload\n"
        "class X:\n"
        "    @overload\n"
        "    def f(self, a: int) -> int: ...\n"
    )
    c = SelfCritic().review(code, "m.py")
    assert not any(f.rule == "stub:empty-function" for f in c.findings)
