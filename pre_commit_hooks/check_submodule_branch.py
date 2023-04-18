from __future__ import annotations

import argparse
import dataclasses
import os
import re
from pathlib import Path
from typing import Iterator
from typing import Sequence

from pre_commit_hooks.util import cmd_output


def parse_gitmodules_properties(
    gitmodules_text: str,
) -> dict[str, dict[str, str]] | None:
    name_re = re.compile(r"\[submodule \"(?P<name>[^\"]+)\"]")
    properties: dict[str, dict[str, str]] = dict()

    sm_name = None
    for line in gitmodules_text.splitlines():
        name_match = name_re.match(line)
        if name_match:
            sm_name = name_match.group('name')
            properties[sm_name] = dict()
        else:
            split = line.split('=', maxsplit=1)
            if len(split) == 2:
                key_raw, value_raw = split
                key = key_raw.strip()
                value = value_raw.strip()
                if sm_name and key:
                    properties[sm_name][key] = value
                else:
                    raise Exception('.gitmodules malformed')
    return properties


@dataclasses.dataclass
class DiffLine:
    mode_src: str
    mode_dst: str
    sha1_src: str
    sha1_dst: str
    status: str
    status_score: int | None
    src: str
    dst: str | None


def get_diff_data(
    from_ref: str | None,
    to_ref: str | None,
    filenames: list[str],
) -> Iterator[DiffLine]:
    if from_ref and to_ref:
        diff_arg = f'{from_ref}...{to_ref}'
    else:
        diff_arg = '--staged'

    diff_out = cmd_output(
        'git', 'diff', '--raw', diff_arg, '--',
    )
    print('DEBUG', 'git', 'diff', '--raw', diff_arg, '--')
    print('DEBUG', 'diff_out\n' + diff_out)

    for line in diff_out.splitlines():
        fields = line.split('\t', 1)
        modes = fields[0].split(' ')
        src = fields[1]
        dst = None
        if len(fields) > 2:
            dst = fields[2]
        mode_src = modes[0].replace(':', '')
        status_score = None
        if len(modes[4]) > 1:
            status_score = int(modes[4][1:])
        yield DiffLine(
            mode_src=mode_src,
            mode_dst=modes[1],
            sha1_src=modes[2],
            sha1_dst=modes[3],
            status=modes[4][0],
            status_score=status_score,
            src=src,
            dst=dst,
        )


def update_branch_prop_in_gitmodules_text(
    gitmodules_text: str,
    mod_name: str,
    new_branch: str,
) -> str:
    mod_branch_re = re.compile(
        fr"(\[submodule \"{mod_name}\"](\s[^\[]+)+branch\s?=\s?)(.+)(\r?\n)?",
    )
    # check if submodule currently has a branch
    if mod_branch_re.match(gitmodules_text):
        # if it currently has a branch, update branch
        return mod_branch_re.sub(
            fr'\g<1>{new_branch}',
            gitmodules_text,
        )
    else:
        # if it doesn't have a branch, add branch
        linebreak = '\r\n' if '\r\n' in gitmodules_text else '\n'
        return re.sub(
            fr"(\[submodule \"{mod_name}\"]){linebreak}",
            fr'\g<1>{linebreak}\tbranch = {new_branch}',
            gitmodules_text,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-unset', action='store_true')
    parser.add_argument('--update-gitmodules-file', action='store_true')
    parser.add_argument('filenames', nargs='*')
    args = parser.parse_args(argv)

    from_ref = os.environ.get('PRE_COMMIT_FROM_REF')
    to_ref = os.environ.get('PRE_COMMIT_TO_REF')

    gitmodules_path = Path('.gitmodules')
    gitmodules_text = None
    gitmodules_properties = None
    if gitmodules_path.exists():
        gitmodules_text = gitmodules_path.read_text()
        gitmodules_properties = parse_gitmodules_properties(gitmodules_text)

    diff_data = get_diff_data(
        from_ref=from_ref,
        to_ref=to_ref,
        filenames=args.filenames,
    )
    retv = 0
    gitmodules_text_changed = False
    for diff_line in diff_data:
        print('DEBUG', 'diff_line', diff_line)
        if diff_line.mode_dst == '160000':
            # It's a submodule
            submodule_path = diff_line.src
            if diff_line.status in ('C', 'R') and diff_line.dst:
                # For copy and rename we check the destination
                submodule_path = diff_line.dst

            submodule_name = None
            submodule_props: dict[str, str] | None = None
            if gitmodules_properties:
                for name, props in gitmodules_properties.items():
                    if submodule_path == props['path']:
                        submodule_name = name
                        submodule_props = props
                        break
            props_branch = None
            if submodule_props and 'branch' in submodule_props:
                props_branch = submodule_props['branch']
            if not args.allow_unset:
                if not submodule_props:
                    retv += 1
                    print(
                        f'No submodule `{submodule_path}` found in '
                        f'`.gitmodules`. This happens when a submodule '
                        f'is added with `git add` rather than with the '
                        f'`git submodule` command.',
                    )
                elif not props_branch:
                    retv += 1
                    print(
                        f'Property `branch` unset for submodule '
                        f'`{submodule_name}`.',
                    )

            branch_prop_needs_update = False
            if props_branch:
                print(
                    'DEBUG', 'cmd_output\n',
                    'git',
                    'branch',
                    props_branch,
                    '--contains',
                    diff_line.sha1_dst,
                )
                on_branch_out = cmd_output(
                    'git',
                    'branch',
                    props_branch,
                    '--contains',
                    diff_line.sha1_dst,
                    '--',
                    cwd=submodule_path,
                )
                print('DEBUG', 'on_branch_out\n' + on_branch_out)
                if props_branch not in on_branch_out:
                    retv += 1
                    branch_prop_needs_update = True
                    print(
                        f'The commit of the submodule `{submodule_path}` '
                        f'is not part of the configured branch '
                        f'`{props_branch}`.',
                    )
            else:
                branch_prop_needs_update = True

            if args.update_gitmodules_file and branch_prop_needs_update:
                abbrev_ref_out = cmd_output(
                    'git',
                    'rev-parse',
                    '--abbrev-ref',
                    'HEAD',
                    cwd=submodule_path,
                )
                print('DEBUG', 'abbrev_ref_out\n' + abbrev_ref_out)
                if abbrev_ref_out == 'HEAD':
                    if not props_branch and not args.allow_unset:
                        print(
                            f'Submodule `{submodule_name}` has a detached '
                            f'HEAD unable to retrieve branch name to update '
                            f'`.gitmodules` file.',
                        )
                elif gitmodules_text and submodule_name:
                    gitmodules_text_changed = True
                    gitmodules_text = update_branch_prop_in_gitmodules_text(
                        gitmodules_text=gitmodules_text,
                        mod_name=submodule_name,
                        new_branch=abbrev_ref_out,
                    )

    if gitmodules_text_changed and gitmodules_text is not None:
        gitmodules_path.write_text(gitmodules_text)

    return retv


if __name__ == '__main__':
    raise SystemExit(main())
