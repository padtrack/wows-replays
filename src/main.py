from typing import Any
import argparse
import array
import enum
import json
import os
import sys


from packaging import version
from replay_unpack.parser import ReplayParser


DESCRIPTION = """\
Utilities for parsing .wowsreplay files and generating 
timelapse videos similar to the in-game minimap. 

Currently, only game version 12.6.0 is supported."""


def default(obj: Any):
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    elif isinstance(obj, enum.Enum):
        return obj.value
    elif isinstance(obj, version.Version):
        return str(obj)
    elif isinstance(obj, array.array):
        return obj.tolist()

    raise ValueError(f"Unable to serialize object of class {object.__class__}")


if __name__ == "__main__":
    # TODO: add description/help

    parser = argparse.ArgumentParser(
        prog="wowsreplays",
        description=DESCRIPTION,
    )
    subparsers = parser.add_subparsers(title="subcommands", dest="command", required=True)

    sub_unpack = subparsers.add_parser("unpack", help="parse replay contents into json output")
    sub_unpack.add_argument("replay", type=argparse.FileType("rb"))
    sub_unpack.add_argument("output", nargs="?", type=argparse.FileType("w"), default=None)
    sub_unpack.add_argument("-p", "--period", type=float, default=0.5)
    sub_unpack.add_argument("--strict", action=argparse.BooleanOptionalAction, default=False)
    sub_unpack.add_argument("--pretty", action=argparse.BooleanOptionalAction, default=False)

    sub_render = subparsers.add_parser("render", help="generate minimap-style timelapse video")
    sub_render.add_argument("replay", type=argparse.FileType("rb"))
    sub_render.add_argument("output", nargs="?", type=argparse.FileType("w"), default=None)
    sub_render.add_argument("-f", "--fps", type=int, default=30)
    sub_render.add_argument("-p", "--period", type=float, default=0.5)
    sub_render.add_argument("-q", "--quality", type=int, choices=range(1, 11), default=8)

    args = parser.parse_args()

    if args.command == "unpack":
        if args.output is None:
            args.output = (
                sys.stdout
                if args.replay.name == "<stdin>"
                else open(os.path.splitext(args.replay.name)[0] + ".replaydata", "w")
            )

        parser = ReplayParser(args.replay, args.strict)
        indent = 4 if args.pretty else None
        args.output.write(
            json.dumps(parser.parse(args.period).model_dump(), indent=indent, default=default)
        )

    if args.command == "render":
        assert args.period > 0, "period must be greater than 0 in render"

        if args.output is None:
            args.output = (
                sys.stdout
                if args.replay.name == "<stdin>"
                else open(os.path.splitext(args.replay.name)[0] + ".mp4", "wb")
            )

        parser = ReplayParser(args.replay, args.strict)
        data = parser.parse(args.period)
