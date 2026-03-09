from __future__ import annotations

import argparse

import legacy_studio as legacy


def cmd_plan_images(args: argparse.Namespace) -> int:
    return legacy.cmd_plan_images(args)


def cmd_generate_images(args: argparse.Namespace) -> int:
    return legacy.cmd_generate_images(args)


def cmd_assemble(args: argparse.Namespace) -> int:
    return legacy.cmd_assemble(args)
