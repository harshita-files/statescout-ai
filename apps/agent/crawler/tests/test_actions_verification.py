import os
import sys

# Ensure project root is in path
project_root = r"c:\Users\jaisu\Projects\fyp"
sys.path.insert(0, project_root)

from apps.agent.crawler.actions import execute_action, launch_session  # noqa: E402


def verify_actions() -> None:
    base_dir = os.path.join(project_root, "test-apps", "broken-rbac-demo")
    login_url = f"file:///{os.path.join(base_dir, 'login.html').replace(os.sep, '/')}"

    print("--- Starting Action Verification ---")

    with launch_session(headless=True) as page:
        # Step 1: Navigate to Login
        print("\n[Step 1] Navigating to login.html...")
        res1 = execute_action(page, {"type": "navigate", "url": login_url})
        if res1["success"]:
            print(f"  Success! Title: {res1['resulting_state']['title']}")
        else:
            print(f"  Failed: {res1['error']}")
            return

        # Step 2: Click 'Continue as Guest'
        print("\n[Step 2] Clicking 'Continue as Guest'...")
        res2 = execute_action(page, {"type": "click", "selector": "#btn-login"})
        if res2["success"]:
            print(f"  Success! Title: {res2['resulting_state']['title']}")
            print(f"  Resulting URL: {res2['resulting_state']['url']}")
        else:
            print(f"  Failed: {res2['error']}")
            return

        # Step 3: Click 'Admin Dashboard' link
        print("\n[Step 3] Clicking 'Admin Dashboard' link in sidebar...")
        res3 = execute_action(page, {"type": "click", "selector": "#nav-admin-dashboard"})
        if res3["success"]:
            print(f"  Success! Title: {res3['resulting_state']['title']}")
            print(f"  Resulting URL: {res3['resulting_state']['url']}")
            # Let's inspect the DOM length or text to prove we reached the admin zone
            print(f"  DOM Length: {len(res3['resulting_state']['dom'])} bytes")
            if "SECURE ZONE: User Management" in res3["resulting_state"]["dom"]:
                print("  Verification: Genuinely reached the Admin page via action execution!")
            else:
                print("  Verification: Did NOT find expected admin text.")
        else:
            print(f"  Failed: {res3['error']}")
            return

    print("\n--- Action Verification Complete ---")


if __name__ == "__main__":
    verify_actions()
