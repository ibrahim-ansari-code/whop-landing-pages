#!/usr/bin/env python3
"""
Quick test that the GitHub App (GITHUB_APP_ID + private key) can authenticate
and access a repo. Run from python-agent dir: python scripts/test_github_app.py [owner/repo]
"""
import sys

# Load .env via config
from config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_PATH, GITHUB_REPO_FULL_NAME
from github_app import get_github_for_repo


def main():
    repo_full_name = (sys.argv[1] if len(sys.argv) > 1 else GITHUB_REPO_FULL_NAME or "").strip()
    if not repo_full_name or repo_full_name == "owner/repo":
        print("Usage: python scripts/test_github_app.py <owner/repo>")
        print("Example: python scripts/test_github_app.py ibrahim-ansari-code/d")
        sys.exit(1)

    print(f"App ID: {GITHUB_APP_ID or '(not set)'}")
    print(f"Key path: {GITHUB_APP_PRIVATE_KEY_PATH or '(not set)'}")
    print(f"Testing repo: {repo_full_name}")
    print()

    gh_repo = get_github_for_repo(repo_full_name)
    if gh_repo is None:
        print("FAIL: Could not get GitHub access (app not installed on this repo or key/config issue).")
        sys.exit(1)

    # Harmless read
    print(f"OK: Got repo {gh_repo.full_name}")
    print(f"    default_branch={gh_repo.default_branch}")
    print("GitHub App auth is working.")


if __name__ == "__main__":
    main()
