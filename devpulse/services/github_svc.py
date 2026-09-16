"""Async GitHub REST client.

One httpx session, opened as a context manager, reused for every call we make
for a given `status` run. API errors get re-mapped to our own exception types
so the CLI layer never has to know about httpx.
"""

import asyncio
from typing import Any

import httpx


class GitHubServiceError(Exception):
    """base error for anything that goes wrong talking to github."""


class GitHubAuthError(GitHubServiceError):
    """401 from the API: token missing, wrong, or expired."""


class GitHubRateLimitError(GitHubServiceError):
    """403 with the rate-limit header drained: back off and retry."""


class GitHubService:
    BASE_URL = "https://api.github.com"
    SEARCH_PER_PAGE = 100
    REQUEST_TIMEOUT = 15.0  # seconds; plenty for an interactive tool

    def __init__(self, base_url: str = BASE_URL):
        self._base_url = base_url.rstrip("/")

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "devpulse",
        }

    async def fetch_user_pull_requests(self, token: str) -> list[dict[str, Any]]:
        """All open PRs owned by the token user, with CI status filled in."""
        token = token.strip()
        if not token:
            raise GitHubAuthError("no token - pass --token or set GITHUB_TOKEN")

        async with httpx.AsyncClient(
            headers=self._auth_headers(token),
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT),
        ) as client:
            search = await self._search_pull_requests(client)
            items = search.get("items") or []
            if not items:
                return []

            # the search API doesn't return each PR's head sha, so we need one
            # detail call + one commit-status call per PR. fire them all at once.
            built = await asyncio.gather(
                *(self._build_pull_request(client, item) for item in items),
                return_exceptions=True,  # one flaky repo shouldn't kill the report
            )
            return [pr for pr in built if isinstance(pr, dict)]

    async def _search_pull_requests(self, client: httpx.AsyncClient) -> dict[str, Any]:
        url = f"{self._base_url}/search/issues"
        params = {"q": "is:open is:pr author:@me", "per_page": self.SEARCH_PER_PAGE}
        return await self._get_json(client, url, params=params)

    async def _build_pull_request(
        self, client: httpx.AsyncClient, item: dict[str, Any]
    ) -> dict[str, Any] | None:
        full_name = self._repo_full_name(item)
        if full_name is None:
            return None  # malformed search item, skip it

        try:
            number = int(item["number"])
        except (KeyError, TypeError, ValueError):
            return None

        owner, repo = full_name.split("/", 1)
        pull = await self._get_json(
            client,
            f"{self._base_url}/repos/{owner}/{repo}/pulls/{number}",
        )

        head = pull.get("head") or {}
        head_sha = head.get("sha")

        ci_status = "no_status"
        if head_sha:
            ci_status = await self._fetch_ci_status(client, owner, repo, head_sha)

        return {
            "number": number,
            "title": item.get("title") or "(untitled)",
            "repository": full_name,
            "branch": head.get("ref") or "?",
            "created_at": pull.get("created_at"),
            "state": pull.get("state"),
            "draft": bool(pull.get("draft", False)),
            "mergeable": pull.get("mergeable"),
            "url": item.get("html_url"),
            "ci_status": ci_status,
        }

    async def _fetch_ci_status(
        self, client: httpx.AsyncClient, owner: str, repo: str, head_sha: str
    ) -> str:
        # combined status endpoint; returns success/failure/pending or nothing
        url = f"{self._base_url}/repos/{owner}/{repo}/commits/{head_sha}/status"
        try:
            data = await self._get_json(client, url)
        except GitHubServiceError:
            return "unknown"  # show it in the table instead of aborting the run
        return data.get("state") or "no_status"

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise GitHubServiceError(
                f"GitHub took too long to answer {url} "
                f"(timed out after {self.REQUEST_TIMEOUT:.0f}s)"
            ) from exc
        except httpx.TransportError as exc:
            raise GitHubServiceError(f"couldn't reach the network: {url} ({exc})") from exc
        except httpx.HTTPStatusError as exc:
            raise self._to_service_error(exc, url) from exc
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"weird HTTP error on {url}: {exc}") from exc
        return response.json()

    @staticmethod
    def _to_service_error(exc: httpx.HTTPStatusError, url: str) -> GitHubServiceError:
        status = exc.response.status_code
        try:
            message = exc.response.json().get("message")
        except ValueError:
            message = None
        message = message or exc.response.text or str(exc)

        if status == 401:
            return GitHubAuthError(
                "GitHub rejected the token (HTTP 401). Double-check GITHUB_TOKEN."
            )
        if status == 403 and exc.response.headers.get("X-RateLimit-Remaining") == "0":
            return GitHubRateLimitError(
                "hit the GitHub rate limit (HTTP 403). wait a bit and retry."
            )
        return GitHubServiceError(f"GitHub said HTTP {status} on {url}: {message}")

    @staticmethod
    def _repo_full_name(item: dict[str, Any]) -> str | None:
        """'owner/repo' from something like .../repos/octocat/hello-world."""
        repo_url = item.get("repository_url") or ""
        marker = "/repos/"
        if marker not in repo_url:
            return None
        name = repo_url.split(marker, 1)[1].strip("/")
        return name or None