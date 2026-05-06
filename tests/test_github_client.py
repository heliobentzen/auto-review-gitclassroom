"""Tests for GitHubClient repository traversal."""

from __future__ import annotations

from types import SimpleNamespace

from src.github_client import GitHubClient


def _dir(path: str):
    return SimpleNamespace(type="dir", path=path)


def _file(path: str, content: str):
    return SimpleNamespace(
        type="file",
        path=path,
        size=len(content.encode("utf-8")),
        decoded_content=content.encode("utf-8"),
    )


class TestGitHubClient:
    def test_skips_common_generated_directories(self, mocker):
        repo = mocker.MagicMock()
        repo.get_contents.side_effect = lambda path: {
            "": [_dir("src"), _dir("node_modules"), _dir("build")],
            "src": [_file("src/MainActivity.kt", "fun main() = Unit")],
        }[path]

        client = GitHubClient("fake-token")
        client.g = mocker.MagicMock()
        client.g.get_repo.return_value = repo
        files = client.get_repo_files("owner/repo")

        assert files == {"src/MainActivity.kt": "fun main() = Unit"}
        visited_paths = [call.args[0] for call in repo.get_contents.call_args_list]
        assert visited_paths == ["", "src"]

    def test_only_includes_main_activity(self, mocker):
        repo = mocker.MagicMock()
        repo.get_contents.side_effect = lambda path: {
            "": [_dir("app")],
            "app": [
                _file("app/MainActivity.kt", "class MainActivity"),
                _file("app/OtherScreen.kt", "class OtherScreen"),
            ],
        }[path]

        client = GitHubClient("fake-token")
        client.g = mocker.MagicMock()
        client.g.get_repo.return_value = repo

        files = client.get_repo_files("owner/repo", extensions=[".kt"])

        assert files == {"app/MainActivity.kt": "class MainActivity"}

    def test_should_skip_nested_generated_directories(self):
        assert GitHubClient._should_skip_dir("node_modules") is True
        assert GitHubClient._should_skip_dir("frontend/node_modules") is False
        assert GitHubClient._should_skip_dir("android/build") is True
        assert GitHubClient._should_skip_dir("android/build/intermediates") is True
        assert GitHubClient._should_skip_dir("src/components") is False

    def test_should_include_only_main_activity_filename(self):
        assert GitHubClient._should_include_file("app/src/MainActivity.kt") is True
        assert GitHubClient._should_include_file("app/src/OtherScreen.kt") is False