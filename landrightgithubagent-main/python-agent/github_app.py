"""
GitHub App auth: get a Github instance for a given repo so the agent
can push to repos under any account that has installed the app.
"""
import logging
import time
from pathlib import Path

from config import (
    GITHUB_APP_ID,
    GITHUB_APP_PRIVATE_KEY,
    GITHUB_APP_PRIVATE_KEY_PATH,
)

log = logging.getLogger(__name__)
_github_cache: dict[int, tuple[object, float]] = {}
_CACHE_TTL_SEC = 50 * 60


def _get_private_key() -> str:
    if GITHUB_APP_PRIVATE_KEY:
        return GITHUB_APP_PRIVATE_KEY.strip()
    if GITHUB_APP_PRIVATE_KEY_PATH:
        path = Path(GITHUB_APP_PRIVATE_KEY_PATH).expanduser().resolve()
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def get_github_for_repo(repo_full_name: str):
    if not GITHUB_APP_ID or not _get_private_key():
        return None
    parts = repo_full_name.split("/", 1)
    if len(parts) != 2:
        return None
    owner, repo = parts[0].strip(), parts[1].strip()
    if not owner or not repo:
        return None
    try:
        from github import GithubIntegration
    except ImportError:
        log.warning("PyGithub not installed or missing GithubIntegration")
        return None
    try:
        key = _get_private_key()
        if "\\n" in key:
            key = key.replace("\\n", "\n")
        integration = GithubIntegration(GITHUB_APP_ID, key)
        installation = integration.get_repo_installation(owner, repo)
        if not installation:
            return None
        iid = installation.id
        now = time.time()
        if iid in _github_cache:
            gh, exp = _github_cache[iid]
            if exp > now:
                return gh.get_repo(repo_full_name)
        gh = integration.get_github_for_installation(iid)
        _github_cache[iid] = (gh, now + _CACHE_TTL_SEC)
        return gh.get_repo(repo_full_name)
    except Exception as e:
        log.warning("GitHub App for %s failed: %s", repo_full_name, e)
    return None
