from graph.fingerprint import fingerprint


def test_dynamic_ids_removed():

    dom1 = '<div id="a1b2c3d4e5">Login</div>'
    dom2 = '<div id="ff881122aa">Login</div>'

    url = "/login"
    ax = "button Login"

    fp1 = fingerprint(dom1, url, ax)
    fp2 = fingerprint(dom2, url, ax)

    assert fp1 == fp2
