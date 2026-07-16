"""
Helpers to parse Azure DevOps Git URLs and shallow-clone a branch for review.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

logger = logging.getLogger(__name__)

# https://dev.azure.com/{org}/{project}/_git/{repo}
# also: https://user@dev.azure.com/... or https://user:pass@dev.azure.com/...
_DEV_AZURE = re.compile(
    r"^https?://(?:[^/@]+(?::[^/@]*)?@)?dev\.azure\.com/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/?#]+)",
    re.IGNORECASE,
)
# https://{org}.visualstudio.com/{project}/_git/{repo}
_VSO = re.compile(
    r"^https?://(?:[^/@]+(?::[^/@]*)?@)?(?P<org>[^.]+)\.visualstudio\.com(?:/DefaultCollection)?/(?P<project>[^/]+)/_git/(?P<repo>[^/?#]+)",
    re.IGNORECASE,
)


def parse_azure_git_url(url: str) -> dict[str, str]:
    raw = (url or "").strip().rstrip("/")
    if raw.lower().endswith(".git"):
        raw = raw[:-4]
    if not raw:
        raise ValueError("Azure Git URL is required.")

    username = ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        if parsed.username:
            username = unquote(parsed.username)
        # rebuild without credentials for consistent matching
        if parsed.hostname:
            raw = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
            if parsed.query:
                raw += f"?{parsed.query}"
    except Exception:
        pass

    m = _DEV_AZURE.match(raw) or _VSO.match(raw)
    if not m:
        raise ValueError(
            "Unrecognized Azure clone URL. Expected:\n"
            "https://dev.azure.com/{org}/{project}/_git/{repo}\n"
            "or https://{user}@dev.azure.com/{org}/{project}/_git/{repo}"
        )
    org = unquote(m.group("org"))
    project = unquote(m.group("project"))
    repo = unquote(m.group("repo"))
    return {
        "org": org,
        "project": project,
        "repo": repo,
        "username": username or "pat",
        "clone_base": f"https://dev.azure.com/{quote(org)}/{quote(project)}/_git/{quote(repo)}",
    }


def clone_azure_branch(
    *,
    azure_url: str,
    token: str,
    branch: str,
    on_progress=None,
) -> tuple[str, Path]:
    """
    Shallow-clone `branch` into a temp directory.
    Returns (work_dir_path, temp_root_to_cleanup).
    """
    parsed = parse_azure_git_url(azure_url)
    if not token.strip():
        raise ValueError("Azure PAT is required.")
    if not branch.strip():
        raise ValueError("Branch is required.")
    if not shutil.which("git"):
        raise RuntimeError("git is not installed on the backend machine.")

    temp_root = Path(tempfile.mkdtemp(prefix="jessie-review-"))
    dest = temp_root / parsed["repo"]

    # Username from clone URL (e.g. Ruposapp@...) or "pat"; password is the PAT / password.
    user = quote(parsed.get("username") or "pat", safe="")
    auth_url = parsed["clone_base"].replace(
        "https://",
        f"https://{user}:{quote(token.strip(), safe='')}@",
        1,
    )

    if on_progress:
        on_progress({
            "type": "progress",
            "message": f"Cloning Azure branch `{branch}`...",
            "pct": 8,
        })

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--branch", branch.strip(),
        "--single-branch",
        auth_url,
        str(dest),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError("Clone timed out after 5 minutes.") from exc

    if proc.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        err = (proc.stderr or proc.stdout or "git clone failed").strip()
        # Never echo the token if somehow present
        err = err.replace(token.strip(), "***")
        raise RuntimeError(f"Failed to clone branch `{branch}`: {err[:500]}")

    if on_progress:
        on_progress({
            "type": "progress",
            "message": f"Clone ready — starting code review on `{branch}`...",
            "pct": 15,
        })

    return str(dest), temp_root


def cleanup_clone(temp_root: Path | None) -> None:
    if temp_root and temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
