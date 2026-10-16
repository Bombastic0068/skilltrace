import base64
import os
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"
MAX_FILE_SIZE = 50 * 1024  # 50 KB

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".sql",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".toml",
    ".sh",
}
SPECIAL_FILENAMES = {"dockerfile", "requirements.txt"}
TEST_DIR_NAMES = {"tests", "test"}
SKIP_DIR_NAMES = {"node_modules", "venv", ".venv", "env"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".bmp",
    ".tiff",
}


def _github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is missing. Put it in your .env file.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def parse_github_url(repo_url: str) -> tuple[str, str]:
    """Turn a GitHub URL into (owner, repo)."""
    parsed = urlparse(repo_url.strip())
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Could not parse GitHub repo URL: {repo_url}")
    owner, repo = parts[0], parts[1]
    return owner, repo


def github_blob_url(repo_url: str, commit_sha: str, path: str) -> str:
    """Build a GitHub web URL for a file at a specific commit."""
    owner, repo = parse_github_url(repo_url)
    encoded_path = quote(path, safe="/")
    return f"https://github.com/{owner}/{repo}/blob/{commit_sha}/{encoded_path}"


def _is_in_tests_folder(path: str) -> bool:
    folders = path.split("/")[:-1]
    return any(folder.lower() in TEST_DIR_NAMES for folder in folders)


def _is_code_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name.lower() in SPECIAL_FILENAMES:
        return True
    if _is_in_tests_folder(path):
        return True
    _, ext = os.path.splitext(name)
    return ext.lower() in CODE_EXTENSIONS


def _should_skip_path(path: str) -> bool:
    parts = path.split("/")
    if any(part in SKIP_DIR_NAMES for part in parts):
        return True
    _, ext = os.path.splitext(path)
    if ext.lower() in IMAGE_EXTENSIONS:
        return True
    return False


def _request(method: str, url: str, **kwargs) -> requests.Response:
    response = requests.request(method, url, headers=_github_headers(), timeout=30, **kwargs)
    if response.status_code == 401:
        raise RuntimeError("GitHub rejected the token. Check GITHUB_TOKEN in .env.")
    if response.status_code == 403:
        raise RuntimeError(f"GitHub rate limit or permission error: {response.text}")
    if response.status_code == 404:
        raise RuntimeError(f"GitHub resource not found: {url}")
    response.raise_for_status()
    return response


def get_latest_commit(repo_url: str) -> dict[str, str]:
    """Return the latest commit hash and message for the repo's default branch."""
    owner, repo = parse_github_url(repo_url)
    repo_info = _request("GET", f"{GITHUB_API}/repos/{owner}/{repo}").json()
    default_branch = repo_info.get("default_branch", "main")
    commits = _request(
        "GET",
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        params={"sha": default_branch, "per_page": 1},
    ).json()
    if not commits:
        raise RuntimeError(f"No commits found for {owner}/{repo}")
    latest = commits[0]
    message = latest["commit"]["message"].strip()
    first_line = message.splitlines()[0]
    return {
        "sha": latest["sha"],
        "message": message,
        "short_message": first_line,
        "branch": default_branch,
    }


def _list_tree_files(owner: str, repo: str, sha: str) -> list[dict]:
    tree_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{sha}"
    data = _request("GET", tree_url, params={"recursive": "1"}).json()
    if data.get("truncated"):
        raise RuntimeError(
            "Repo tree is too large for one GitHub API call. Try a smaller repository."
        )
    return [item for item in data.get("tree", []) if item.get("type") == "blob"]


def _read_file_content(owner: str, repo: str, path: str, sha: str) -> str:
    blob = _request("GET", f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs/{sha}").json()
    encoding = blob.get("encoding")
    content = blob.get("content", "")
    if encoding == "base64":
        raw = base64.b64decode(content)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")
    if isinstance(content, str):
        return content
    return ""


def list_code_files(repo_url: str) -> list[dict]:
    """List allowed code files and read their contents from a GitHub repo."""
    owner, repo = parse_github_url(repo_url)
    latest = get_latest_commit(repo_url)
    files: list[dict] = []

    for item in _list_tree_files(owner, repo, latest["sha"]):
        path = item.get("path", "")
        size = int(item.get("size") or 0)
        if not path or _should_skip_path(path) or not _is_code_file(path):
            continue
        if size > MAX_FILE_SIZE:
            continue
        files.append(
            {
                "path": path,
                "size": size,
                "content": _read_file_content(owner, repo, path, item["sha"]),
            }
        )

    files.sort(key=lambda item: item["path"])
    return files
