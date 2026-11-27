import pytest

from safepilot_ci.repo import RepoLayout, RepoNotFound, find_repo_root
from tests.fakes import FULL_REPO, make_repo


def test_find_repo_root_walks_up(tmp_path):
    root = make_repo(tmp_path, "backend/app")
    assert find_repo_root(root / "backend" / "app") == root.resolve()


def test_find_repo_root_fails_outside_a_repo(tmp_path):
    with pytest.raises(RepoNotFound):
        find_repo_root(tmp_path)


def test_scan_full_repo(tmp_path):
    layout = RepoLayout.scan(make_repo(tmp_path, *FULL_REPO))
    assert layout.python_paths == ("backend/app", "sandbox-runner")
    assert layout.backend_requirements and layout.backend_tests
    assert layout.frontend and layout.sandbox_runner and layout.demo_target


def test_scan_empty_repo(tmp_path):
    layout = RepoLayout.scan(make_repo(tmp_path))
    assert layout.python_paths == ()
    assert not any([layout.backend_tests, layout.frontend, layout.sandbox_runner])


def test_stale_tests_dir_without_test_files_is_not_a_suite(tmp_path):
    layout = RepoLayout.scan(make_repo(tmp_path, "backend/tests/__pycache__"))
    assert not layout.backend_tests
