from __future__ import annotations

import argparse

import legacy_studio as legacy


def cmd_score(args: argparse.Namespace) -> int:
    return legacy.cmd_score(args)


def build_score_report(*args, **kwargs):
    return legacy.build_score_report(*args, **kwargs)
