# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

"""VeraLux names for the generic upstream checker in ``afternight_repo.upstream``."""

from afternight_repo.upstream import UpstreamError, check_upstream, format_upstream_report


VeraLuxUpstreamError = UpstreamError


def check_veralux_upstream(package_dir, upstream_checkout, ref=None):
    """Compare VeraLux UPSTREAM.json entries against a local upstream git checkout."""

    return check_upstream(package_dir, upstream_checkout, ref=ref)


def format_veralux_upstream_report(report):
    return format_upstream_report(report, title="VeraLux upstream check")
