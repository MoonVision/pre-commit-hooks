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
[submodule "b"]
\tpath = b
\turl = ../repo_b
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
        subprocess.check_call(
            (
                'git', '-c', 'protocol.file.allow=always', 'submodule',
                'add', '../repo_a', 'a',
            ),
            cwd='repo',
        )
        subprocess.check_call(
            ('git', 'checkout', '-b', 'branch_a'),
            cwd='repo/a',
        )
        subprocess.check_call(
            (
                'git', '-c', 'protocol.file.allow=always', 'submodule',
                'add', '../repo_b', 'b',
            ),
            cwd='repo',
        )
        subprocess.check_call(
            ('git', 'checkout', '-b', 'branch_b'),
            cwd='repo/b',
        )
        subprocess.check_call(('git', 'add', '.'), cwd='repo')
        git_commit('-m', 'add submodules', cwd='repo')
        os.chdir('repo')
        yield


def test_repo_with_submodules_has_expected_gitmodules(repo_with_submodules):
    assert Path('.gitmodules').read_text() == GITMODULES_REPO


def test_main_no_complaints(repo_with_submodules):
    git_commit('--allow-empty', '-m', 'init', cwd='a')
    assert main(()) == 0
