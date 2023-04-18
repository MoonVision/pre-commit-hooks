import argparse
import dataclasses
import os
import re
from pathlib import Path
from typing import Sequence, Iterator, Optional, Dict

from pre_commit_hooks.util import cmd_output


def parse_gitmodules_properties(gitmodules_text: str) -> Optional[Dict[str, Dict[str, str]]]:
    name_re = re.compile(r"\[submodule \"(?P<name>[^\"]+)\"]")
    properties = dict()

    sm_name = None
    for line in gitmodules_text.splitlines():
        name_match = name_re.match(line)
        if name_match:
            sm_name = name_match.group("name")
            properties[sm_name] = dict()
        else:
            split = line.split("=", maxsplit=1)
            if len(split) == 2:
                key_raw, value_raw = split
                key = key_raw.strip()
                value = value_raw.strip()
                properties[sm_name][key] = value
    return properties


@dataclasses.dataclass
class DiffLine:
    mode_src: str
    mode_dst: str
    sha1_src: str
    sha1_dst: str
    status: str
    status_score: Optional[int]
    src: str
    dst: Optional[str]


def get_diff_data(from_ref: Optional[str], to_ref: Optional[str], filenames: list[str]) -> Iterator[DiffLine]:
    if from_ref and to_ref:
        diff_arg = f"{from_ref}...{to_ref}"
    else:
        diff_arg = "--staged"

    diff_out = cmd_output(
        "git", "diff", "--diff-filter=A", "--raw", diff_arg, "--",
        *filenames,
    )

    for line in diff_out.splitlines():
        fields = line.split("\t", 1)
        modes = fields[0]
        src = fields[1]
        dst = None
        if len(fields) >= 2:
            dst = fields[2]
        mode_src = modes[0].replace(":", "")
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-unset", action="store_true")
    parser.add_argument("--update-gitmodules-file", action="store_true")
    parser.add_argument("filenames", nargs="*")
    args = parser.parse_args(argv)

    from_ref = os.environ.get("PRE_COMMIT_FROM_REF")
    to_ref = os.environ.get("PRE_COMMIT_TO_REF")

    gitmodules_path = Path(".gitmodules")
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
        if diff_line.mode_dst == "160000":
            # It"s a submodule
            submodule_path = diff_line.src
            if diff_line.status in ("C", "R"):
                # For copy and rename we check the destination
                submodule_path = diff_line.dst

            submodule_name = None
            submodule_props: Optional[Dict[str, str]] = None
            if gitmodules_properties:
                for name, props in gitmodules_properties:
                    if submodule_path == props["path"]:
                        submodule_name = name
                        submodule_props = props
                        break
            props_branch = submodule_props.get("branch", None)
            if not args.allow_unset:
                if not submodule_props:
                    retv += 1
                    print(
                        f"No submodule `{submodule_path}` found in `.gitmodules`. "
                        f"This happens when a submodule is added with `git add` rather "
                        f"than with the `git submodule` command."
                    )
                elif not props_branch:
                    retv += 1
                    print(f"Property `branch` unset for submodule `{submodule_name}`.")

            branch_prop_needs_update = False
            if props_branch:
                on_branch_out = cmd_output("git", "branch", props_branch, "--contains", diff_line.sha1_dst)
                if props_branch not in on_branch_out:
                    retv += 1
                    branch_prop_needs_update = True
                    print(f"The submodule commit is not part of the configured branch `{props_branch}`.")
            else:
                branch_prop_needs_update = True

            if args.update_gitmodules_file and branch_prop_needs_update:
                abbrev_ref_out = cmd_output("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=submodule_path)
                if abbrev_ref_out == "HEAD":
                    if not props_branch and not args.allow_unset:
                        print(
                            f"Submodule `{submodule_name}` has a detached HEAD "
                            f"unable to retrieve branch name to update `.gitmodules` file."
                        )
                else:
                    gitmodules_text_changed = True
                    gitmodules_text = re.sub(
                        fr"(\[submodule \"{submodule_name}\"](\s.+)+branch\s?=\s?)(.+)",
                        fr"\g<1>{abbrev_ref_out}",
                        gitmodules_text,
                    )

    if gitmodules_text_changed:
        gitmodules_path.write_text(gitmodules_text)

    return retv


if __name__ == "__main__":
    raise SystemExit(main())
