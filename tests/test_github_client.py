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

    def test_prioritizes_relevant_kotlin_files(self, mocker):
        repo = mocker.MagicMock()
        repo.get_contents.side_effect = lambda path: {
            "": [_dir("app")],
            "app": [
                _file("app/MainActivity.kt", "class MainActivity"),
                _file("app/OtherScreen.kt", "class OtherScreen"),
                _file("app/NavigationGraph.kt", "class NavigationGraph"),
                _file("app/UnusedModel.kt", "class UnusedModel"),
            ],
        }[path]

        client = GitHubClient("fake-token")
        client.g = mocker.MagicMock()
        client.g.get_repo.return_value = repo

        files = client.get_repo_files("owner/repo", extensions=[".kt"])

        assert files == {
            "app/MainActivity.kt": "class MainActivity",
            "app/OtherScreen.kt": "class OtherScreen",
            "app/NavigationGraph.kt": "class NavigationGraph",
            "app/UnusedModel.kt": "class UnusedModel",
        }

    def test_should_skip_nested_generated_directories(self):
        assert GitHubClient._should_skip_dir("node_modules") is True
        assert GitHubClient._should_skip_dir("frontend/node_modules") is False
        assert GitHubClient._should_skip_dir("android/build") is True
        assert GitHubClient._should_skip_dir("android/build/intermediates") is True
        assert GitHubClient._should_skip_dir("src/components") is False

    def test_relevance_prioritizes_main_and_navigation_files(self):
        ranked = sorted(
            [
                "app/src/UnusedModel.kt",
                "app/src/ScreenB.kt",
                "app/src/MainActivity.kt",
            ],
            key=GitHubClient._relevance_key,
        )

        assert ranked[0] == "app/src/MainActivity.kt"
        assert ranked[1] == "app/src/ScreenB.kt"

    def test_prioritizes_general_entry_files_for_other_languages(self, mocker):
        repo = mocker.MagicMock()
        repo.get_contents.side_effect = lambda path: {
            "": [_dir("src")],
            "src": [
                _file("src/helpers.py", "def helper(): pass"),
                _file("src/main.py", "print('run')"),
                _file("src/controllers.py", "def controller(): pass"),
                _file("src/models.py", "class Model: pass"),
                _file("src/test_app.py", "def test_ok(): pass"),
            ],
        }[path]

        client = GitHubClient("fake-token")
        client.g = mocker.MagicMock()
        client.g.get_repo.return_value = repo

        files = client.get_repo_files("owner/repo", extensions=[".py"])

        assert list(files)[:2] == ["src/main.py", "src/controllers.py"]
        assert "src/test_app.py" not in files
        assert set(files) == {
            "src/main.py",
            "src/controllers.py",
            "src/helpers.py",
            "src/models.py",
        }