"""GitHub REST API wrapper for repository file access and issue creation."""

from __future__ import annotations

from github import Github, GithubException


# File extensions considered as source code by default.
DEFAULT_CODE_EXTENSIONS = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".cs",
    ".go",
    ".rb",
    ".php",
    ".html",
    ".css",
    ".scss",
    ".sh",
    ".rs",
    ".kt",
    ".swift",
)

# Maximum individual file size (bytes) to attempt decoding.
MAX_FILE_BYTES = 100_000


class GitHubClient:
    """Thin wrapper around PyGithub for the operations this tool needs."""

    def __init__(self, token: str) -> None:
        self.g = Github(token)

    # ------------------------------------------------------------------
    # Repository file reading
    # ------------------------------------------------------------------

    def get_repo_files(
        self,
        repo_full_name: str,
        extensions: list[str] | None = None,
    ) -> dict[str, str]:
        """Return a mapping of ``path -> text content`` for a repository.

        Parameters
        ----------
        repo_full_name:
            GitHub repository in ``owner/repo`` format.
        extensions:
            Whitelist of file extensions (e.g. ``[".py", ".js"]``).
            If *None* or empty the :data:`DEFAULT_CODE_EXTENSIONS` set is used.
        """
        allowed = tuple(extensions) if extensions else DEFAULT_CODE_EXTENSIONS
        repo = self.g.get_repo(repo_full_name)
        files: dict[str, str] = {}
        self._traverse(repo, "", files, allowed)
        return files

    def _traverse(
        self,
        repo,
        path: str,
        files: dict[str, str],
        extensions: tuple[str, ...],
    ) -> None:
        try:
            contents = repo.get_contents(path)
        except GithubException:
            return

        if not isinstance(contents, list):
            contents = [contents]

        for item in contents:
            if item.type == "dir":
                self._traverse(repo, item.path, files, extensions)
            elif item.type == "file":
                if item.path.endswith(extensions) and item.size <= MAX_FILE_BYTES:
                    try:
                        files[item.path] = item.decoded_content.decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # Issue creation
    # ------------------------------------------------------------------

    def create_issue(
        self,
        repo_full_name: str,
        title: str,
        body: str,
    ) -> str:
        """Create a GitHub issue and return its URL.

        Parameters
        ----------
        repo_full_name:
            GitHub repository in ``owner/repo`` format.
        title:
            Issue title.
        body:
            Issue body (Markdown).

        Returns
        -------
        str
            The HTML URL of the created issue.
        """
        repo = self.g.get_repo(repo_full_name)
        issue = repo.create_issue(title=title, body=body)
        return issue.html_url
