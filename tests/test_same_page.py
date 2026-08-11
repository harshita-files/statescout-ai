from graph.fingerprint import fingerprint


def test_same_page_same_hash():

    dom = '<div id="abc123456">Login</div>'
    url = "/login"
    ax = "button Login"

    fp1 = fingerprint(dom, url, ax)
    fp2 = fingerprint(dom, url, ax)

    assert fp1 == fp2