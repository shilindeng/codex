from __future__ import annotations

import argparse

import legacy_studio as legacy


def cmd_render(args: argparse.Namespace) -> int:
    return legacy.cmd_render(args)
