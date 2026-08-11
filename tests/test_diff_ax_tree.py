from graph.fingerprint import fingerprint


def test_different_ax_tree():

    dom = "<button></button>"
    url = "/"

    fp1 = fingerprint(dom, url, "Button Login")
    fp2 = fingerprint(dom, url, "Button Logout")

    assert fp1 != fp2
