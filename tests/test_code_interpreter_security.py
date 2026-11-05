"""Security regression tests for the sandboxed code interpreter.

Guards against namespace-escape -> arbitrary command execution (P0).
The interpreter must run untrusted code in an isolated subprocess with a
stripped builtins namespace; even a successful namespace escape must only
touch the throwaway process, never ORBIT memory/secrets, and the validator
must reject the escape vectors outright.
"""

import pytest

from orbit.orbit.core.code_interpreter import get_code_interpreter


@pytest.fixture
def ci():
    return get_code_interpreter()


def test_subclasses_sandbox_escape_is_blocked(ci):
    """__subclasses__() -> os._wrap_close -> os.system must NOT execute."""
    payload = (
        "subs = (1).__class__.__bases__[0].__subclasses__()\n"
        "wrap = [c for c in subs if c.__name__ == '_wrap_close'][0]\n"
        "system_fn = wrap.__init__.__globals__['system']\n"
        "system_fn('echo PWNED_ESCAPE > C:\\\\tmp\\\\should_not_exist.txt')\n"
    )
    r = ci.execute(payload)
    assert r.status == "blocked", r.error


def test_dunder_attribute_access_blocked(ci):
    r = ci.execute("x = (1).__class__")
    assert r.status == "blocked"


def test_getattr_obfuscation_blocked(ci):
    r = ci.execute("getattr(__builtins__, '__import__')")
    assert r.status == "blocked"


def test_banned_import_blocked(ci):
    r = ci.execute("import os\nos.system('echo x')")
    assert r.status == "blocked"


def test_no_filesystem_access(ci):
    # 'open' is blocked at validation time -> "Dangerous builtin" or not in builtins -> NameError.
    r = ci.execute("open('/tmp/x', 'w').write('z')")
    assert r.status != "success"
    assert (
        "not defined" in r.error
        or "Dangerous builtin" in r.error
        or "blocked" in r.status
    )


def test_no_network_access(ci):
    r = ci.execute(
        "import urllib.request\nurllib.request.urlopen('http://example.com')"
    )
    assert r.status == "blocked"


def test_legit_code_runs(ci):
    r = ci.execute("print(2 + 3)")
    assert r.status == "success"
    assert "5" in r.output


def test_stateful_session_preserved(ci):
    ci.execute("counter = 10")
    r = ci.execute("counter = counter + 1\nprint(counter)")
    assert r.status == "success"
    assert "11" in r.output
