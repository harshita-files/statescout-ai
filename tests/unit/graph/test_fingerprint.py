"""
Unit tests for apps.agent.graph.fingerprint

Tests cover both normalize_state (the normalization logic) and fingerprint
(the SHA-256 hashing layer).  No external services required.

Run:  pytest tests/unit/test_fingerprint.py -v
"""

from apps.agent.graph.fingerprint import fingerprint, normalize_state


class TestNormalizeState:
    def test_identical_pages_with_different_session_ids(self):
        """Same page, different data-session value → must normalize identically."""
        state_1 = normalize_state(
            '<div data-session="sess_abc123">Content</div>',
            "/dashboard",
            "heading Dashboard",
        )
        state_2 = normalize_state(
            '<div data-session="sess_xyz789">Content</div>',
            "/dashboard",
            "heading Dashboard",
        )
        assert state_1 == state_2

    def test_identical_pages_with_different_dynamic_ids(self):
        """Same page, different hex form id → must normalize identically."""
        state_1 = normalize_state(
            '<form id="form-3f9a1b">Email</form>',
            "/login",
            "form",
        )
        state_2 = normalize_state(
            '<form id="form-8c02de">Email</form>',
            "/login",
            "form",
        )
        assert state_1 == state_2

    def test_different_pages_stay_different(self):
        """Guest page (no admin link) vs admin page (admin link) → must differ."""
        guest = normalize_state(
            '<nav><a href="/home">Home</a></nav>',
            "/dashboard",
            "navigation",
        )
        admin = normalize_state(
            '<nav><a href="/home">Home</a><a href="/admin">Admin</a></nav>',
            "/dashboard",
            "navigation",
        )
        assert guest != admin

    def test_url_difference_matters(self):
        """Same DOM, different URLs → must produce different normalizations."""
        state_1 = normalize_state("<h1>Home</h1>", "/", "heading Home")
        state_2 = normalize_state("<h1>Home</h1>", "/login", "heading Home")
        assert state_1 != state_2

    def test_whitespace_variations_dont_matter(self):
        """Extra / indented whitespace in HTML → must normalize identically."""
        state_1 = normalize_state("<h1>Home</h1>", "/", "heading Home")
        state_2 = normalize_state(
            """
            <h1>
                Home
            </h1>
            """,
            "/",
            "heading Home",
        )
        assert state_1 == state_2

    def test_timestamps_stripped(self):
        """Long numeric timestamps embedded in DOM → stripped during normalization."""
        state_1 = normalize_state("<span>1717171717</span>", "/dashboard", "Dashboard")
        state_2 = normalize_state("<span>1818181818</span>", "/dashboard", "Dashboard")
        assert state_1 == state_2

    def test_csrf_token_stripped(self):
        """data-csrf attribute value should be stripped like data-session."""
        state_1 = normalize_state(
            '<input data-csrf="csrf_aabbccdd">',
            "/form",
            "form",
        )
        state_2 = normalize_state(
            '<input data-csrf="csrf_11223344">',
            "/form",
            "form",
        )
        assert state_1 == state_2


class TestFingerprint:
    def test_fingerprint_is_sha256_hex(self):
        """Fingerprint must be a 64-character lowercase hex string (SHA-256)."""
        fp = fingerprint("<h1>Home</h1>", "/", "heading Home")
        assert isinstance(fp, str)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_identical_states_have_identical_fingerprints(self):
        """Two calls with identical inputs must produce the same fingerprint."""
        fp_1 = fingerprint("<h1>Home</h1>", "/", "heading Home")
        fp_2 = fingerprint("<h1>Home</h1>", "/", "heading Home")
        assert fp_1 == fp_2

    def test_different_states_have_different_fingerprints(self):
        """Different states must not collide."""
        fp_1 = fingerprint("<h1>Home</h1>", "/", "heading Home")
        fp_2 = fingerprint("<h1>Login</h1>", "/login", "heading Login")
        assert fp_1 != fp_2
