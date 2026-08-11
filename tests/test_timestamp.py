from graph.fingerprint import fingerprint


def test_timestamp_removed():

    dom1 = "<span>1717171717</span>"
    dom2 = "<span>1818181818</span>"

    url = "/dashboard"
    ax = "Dashboard"

    fp1 = fingerprint(dom1, url, ax)
    fp2 = fingerprint(dom2, url, ax)

    assert fp1 == fp2
