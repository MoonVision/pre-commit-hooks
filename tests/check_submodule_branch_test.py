from __future__ import annotations

import pytest

from pre_commit_hooks.check_submodule_branch import (
    parse_gitmodules_properties,
)
from pre_commit_hooks.check_submodule_branch import (
    update_branch_prop_in_gitmodules_text,
)

GITMODULES_A_BRANCH_A = '''
[submodule "a"]
\tpath = a_path
\tbranch = a
'''

GITMODULES_A_BRANCH_B = '''
[submodule "a"]
\tpath = a_path
\tbranch = b
'''

GITMODULES_A_B_BRANCH_A_B = '''
[submodule "a"]
\tbranch = a

[submodule "b"]
\tbranch = b
'''


GITMODULES_A_B_BRANCH_A_A = '''
[submodule "a"]
\tbranch = a

[submodule "b"]
\tbranch = a
'''

GITMODULES_A_B_BRANCH_B_B = '''
[submodule "a"]
\tbranch = b

[submodule "b"]
\tbranch = b
'''


@pytest.mark.parametrize(
    'gitmodules_text, expected', [
        (GITMODULES_A_BRANCH_A, {'a': {'branch': 'a', 'path': 'a_path'}}),
        (
            GITMODULES_A_B_BRANCH_A_B,
            {'a': {'branch': 'a'}, 'b': {'branch': 'b'}},
        ),
    ],
)
def test_parse_gitmodules_properties(gitmodules_text, expected):
    result = parse_gitmodules_properties(gitmodules_text)
    assert result == expected


@pytest.mark.parametrize(
    'before, after, module_name, new_branch', [
        (GITMODULES_A_BRANCH_A, GITMODULES_A_BRANCH_B, 'a', 'b'),
        (GITMODULES_A_BRANCH_A, GITMODULES_A_BRANCH_A, 'a', 'a'),
        (GITMODULES_A_B_BRANCH_A_B, GITMODULES_A_B_BRANCH_B_B, 'a', 'b'),
        (GITMODULES_A_B_BRANCH_A_B, GITMODULES_A_B_BRANCH_A_B, 'a', 'a'),
        (GITMODULES_A_B_BRANCH_A_B, GITMODULES_A_B_BRANCH_A_B, 'b', 'b'),
        (GITMODULES_A_B_BRANCH_A_B, GITMODULES_A_B_BRANCH_A_A, 'b', 'a'),
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
