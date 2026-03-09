from __future__ import annotations

import argparse

import legacy_studio as legacy


def cmd_publish(args: argparse.Namespace) -> int:
    return legacy.cmd_publish(args)


def cmd_verify_draft(args: argparse.Namespace) -> int:
    return legacy.cmd_verify_draft(args)
