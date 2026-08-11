from graph.fingerprint import fingerprint


def test_different_dom():

    url = "/home"
    ax = "Home"

    fp1 = fingerprint("<button>Login</button>", url, ax)
    fp2 = fingerprint("<button>Logout</button>", url, ax)

    assert fp1 != fp2
