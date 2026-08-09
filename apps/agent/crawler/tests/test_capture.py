import os
import sys

# Ensure project root is in path so absolute imports work
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
sys.path.insert(0, project_root)

from apps.agent.crawler.capture import capture_page


def test_capture_page_success() -> None:
    """Test successful capture against a local test-app HTML file."""
    # Find the broken-rbac-demo index.html
    test_html = os.path.join(project_root, "test-apps", "broken-rbac-demo", "index.html")
    file_url = f"file:///{test_html.replace(os.sep, '/')}"

    result = capture_page(file_url)

    # Assert structural correctness (fields present and valid types)
    assert result["success"] is True
    assert result["url"] == file_url
    assert "timestamp" in result
    assert isinstance(result["dom"], str)
    assert len(result["dom"]) > 0
    assert isinstance(result["accessibility_tree"], dict)
    assert isinstance(result["screenshot_path"], str)
    assert os.path.exists(result["screenshot_path"])


def test_capture_page_failure() -> None:
    """Test graceful failure on an unreachable URL."""
    result = capture_page("http://localhost:9999/does-not-exist")

    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0
    # ensure structure is preserved
    assert result["dom"] == ""
    assert result["accessibility_tree"] == {}
    assert result["screenshot_path"] == ""
