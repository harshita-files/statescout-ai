from graph.fingerprint import fingerprint


def test_different_url():

    dom = "<div>Login</div>"
    ax = "Login"

    fp1 = fingerprint(dom, "/login", ax)
    fp2 = fingerprint(dom, "/admin", ax)

    assert fp1 != fp2