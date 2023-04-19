from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pre_commit_hooks.check_submodule_branch import main
from pre_commit_hooks.check_submodule_branch import parse_gitmodules_properties
from pre_commit_hooks.check_submodule_branch import (
    update_branch_prop_in_gitmodules_text,
)
from pre_commit_hooks.util import cmd_output
from testing.util import git_commit

GITMODULES_A_BRANCH_A = '''
[submodule "a"]
\tpath = a_path
\tbranch = branch_a
'''

GITMODULES_A_BRANCH_B = '''
[submodule "a"]
\tpath = a_path
\tbranch = branch_b
'''

GITMODULES_A_B_BRANCH_A_B = '''
[submodule "a"]
\tbranch = branch_a

[submodule "b"]
\tbranch = branch_b
'''


GITMODULES_A_B_BRANCH_A_A = '''
[submodule "a"]
\tbranch = branch_a

[submodule "b"]
\tbranch = branch_a
'''

GITMODULES_A_B_BRANCH_B_B = '''
[submodule "a"]
\tbranch = branch_b

[submodule "b"]
\tbranch = branch_b
'''


GITMODULES_MALFORMED_1 = '''
[submodule "a"]
\t= branch_a
'''


GITMODULES_MALFORMED_2 = '''
[submodule ""]
\tbranch = branch_a
'''

GITMODULES_REPO = '''[submodule "a"]
\tpath = a
\turl = ../repo_a
\tbranch = branch_a
[submodule "b"]
\tpath = b
\turl = ../repo_b
\tbranch = branch_b
'''


GITMODULES_REPO_BRANCHES_UNSET = '''[submodule "a"]
\tpath = a
\turl = ../repo_a
[submodule "b"]
\tpath = b
\turl = ../repo_b
'''

GITMODULES_REPO_BRANCH_A_UNSET = '''[submodule "a"]
\tpath = a
\turl = ../repo_a
[submodule "b"]
\tpath = b
\turl = ../repo_b
\tbranch = branch_b
'''


GITMODULES_REPO_UPDATED = '''[submodule "a"]
\tbranch = branch_a
\tpath = a
\turl = ../repo_a
\t
[submodule "b"]
\tpath = b
\turl = ../repo_b
\tbranch = branch_b
'''


@pytest.mark.parametrize(
    'gitmodules_text, expected', [
        (
            GITMODULES_A_BRANCH_A,
            {'a': {'branch': 'branch_a', 'path': 'a_path'}},
        ),
        (
            GITMODULES_A_B_BRANCH_A_B,
            {'a': {'branch': 'branch_a'}, 'b': {'branch': 'branch_b'}},
        ),
    ],
)
def test_parse_gitmodules_properties(gitmodules_text, expected):
    result = parse_gitmodules_properties(gitmodules_text)
    assert result == expected


@pytest.mark.parametrize(
    'gitmodules_text', [
        GITMODULES_MALFORMED_1, GITMODULES_MALFORMED_2,
    ],
)
def test_parse_gitmodules_properties_malformed(gitmodules_text):
    with pytest.raises(Exception) as err:
        parse_gitmodules_properties(gitmodules_text)
    assert err.value.args[0] == '.gitmodules malformed'


@pytest.mark.parametrize(
    'before, after, module_name, new_branch', [
        (GITMODULES_A_BRANCH_A, GITMODULES_A_BRANCH_B, 'a', 'branch_b'),
        (GITMODULES_A_BRANCH_A, GITMODULES_A_BRANCH_A, 'a', 'branch_a'),
        (
            GITMODULES_A_B_BRANCH_A_B,
            GITMODULES_A_B_BRANCH_B_B,
            'a',
            'branch_b',
        ),
        (
            GITMODULES_A_B_BRANCH_A_B,
            GITMODULES_A_B_BRANCH_A_B,
            'a',
            'branch_a',
        ),
        (
            GITMODULES_A_B_BRANCH_A_B,
            GITMODULES_A_B_BRANCH_A_B,
            'b',
            'branch_b',
        ),
        (
            GITMODULES_A_B_BRANCH_A_B,
            GITMODULES_A_B_BRANCH_A_A,
            'b',
            'branch_a',
        ),
        (
            GITMODULES_REPO.replace('branch_a', 'wrong-branch'),
            GITMODULES_REPO,
            'a',
            'branch_a',
        ),
    ],
)
def test_update_branch_prop_in_gitmodules_text(
    before, after, module_name, new_branch,
):
    result = update_branch_prop_in_gitmodules_text(
        before,
        module_name,
        new_branch,
    )
    assert result == after


@pytest.fixture
def repo_with_submodules(tmpdir):
    with tmpdir.as_cwd():
        subprocess.check_call(('git', 'init', 'repo'))
        git_commit('--allow-empty', '-m', 'init', cwd='repo')
        subprocess.check_call(('git', 'init', 'repo_a'))
        git_commit('--allow-empty', '-m', 'init', cwd='repo_a')
        subprocess.check_call(('git', 'init', 'repo_b'))
        git_commit('--allow-empty', '-m', 'init', cwd='repo_b')
        os.chdir('repo')
        subprocess.check_call(
            'git -c protocol.file.allow=always submodule add ../repo_a a'
            .split(' '),
        )
        subprocess.check_call(
            ('git', 'checkout', '-b', 'branch_a'),
            cwd='a',
        )
        subprocess.check_call(
            'git submodule set-branch --branch branch_a a'.split(' '),
        )
        subprocess.check_call(
            'git -c protocol.file.allow=always submodule add ../repo_b b'
            .split(' '),
        )
        subprocess.check_call(
            'git checkout -b branch_b'.split(' '),
            cwd='b',
        )
        subprocess.check_call(
            'git submodule set-branch --branch branch_b b'.split(' '),
        )
        subprocess.check_call(('git', 'add', '.'))
        git_commit('-m', 'add submodules')
        yield


def test_repo_with_submodules_has_expected_gitmodules(repo_with_submodules):
    assert Path('.gitmodules').read_text() == GITMODULES_REPO


def test_main_no_complaints(repo_with_submodules):
    git_commit('--allow-empty', '-m', 'init', cwd='a')
    subprocess.check_call(('git', 'add', '.'))
    assert main(()) == 0


def test_main_branch_mismatch(repo_with_submodules):
    subprocess.check_call(
        ('git', 'checkout', '-b', 'new_branch'),
        cwd='a',
    )
    git_commit('--allow-empty', '-m', 'init', cwd='a')
    subprocess.check_call(('git', 'add', '.'))
    assert main(()) == 1


def test_main_earlier_commit_on_branch_is_fine(repo_with_submodules):
    commit_sha1 = cmd_output('git', 'rev-parse', 'HEAD', cwd='a')
    git_commit('--allow-empty', '-m', 'another commit', cwd='a')
    subprocess.check_call(('git', 'checkout', commit_sha1.strip()), cwd='a')
    assert main(()) == 0


def test_main_gitmodules_changed_branch_wrong_errors(
    repo_with_submodules,
):
    Path('.gitmodules').write_text(
        GITMODULES_REPO.replace('branch_a', 'wrong-branch'),
    )
    subprocess.check_call(('git', 'add', '.gitmodules'))
    assert main(()) == 1


def test_main_gitmodules_branch_unset_errors(repo_with_submodules):
    Path('.gitmodules').write_text(
        GITMODULES_REPO.replace('branch = branch_a', ''),
    )
    subprocess.check_call(('git', 'add', '.gitmodules'))
    assert main(()) == 1


def test_main_gitmodules_branch_unset_doesnt_error_with_allow_unset(
    repo_with_submodules,
):
    Path('.gitmodules').write_text(
        GITMODULES_REPO.replace('branch = branch_a', ''),
    )
    subprocess.check_call(('git', 'add', '.gitmodules'))
    assert main(('--allow-unset',)) == 0


@pytest.mark.parametrize(
    'gitmodules_text, expected', [
        (
            GITMODULES_REPO.replace('branch = branch_a', ''),
            GITMODULES_REPO_UPDATED,
        ),
        (
            GITMODULES_REPO.replace('branch_a', 'wrong-branch'),
            GITMODULES_REPO,
        ),
    ],
)
def test_main_update_gitmodules_file_updates_file(
    repo_with_submodules, gitmodules_text, expected,
):
    Path('.gitmodules').write_text(
        gitmodules_text,
    )
    subprocess.check_call(('git', 'add', '.gitmodules'))
    main(('--update-gitmodules-file',))
    assert Path('.gitmodules').read_text() == expected
