# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Ezequiel Ruiz

"""Shared attribution text for VeraLux AfterNight ports."""

from __future__ import annotations


ORIGINAL_AUTHOR = "Riccardo Paterniti"
PORT_AUTHOR = "Ezequiel Ruiz"
SUITE_NAME = "VeraLux script suite"


def attribution_text(tool_name, source_version):
    return (
        f"AfterNight port of VeraLux {tool_name}, source version {source_version}, originally authored by "
        f"{ORIGINAL_AUTHOR} for the {SUITE_NAME}. AfterNight port by {PORT_AUTHOR}."
    )
