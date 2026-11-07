# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Adrian Knagg-Baugh
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (GaiaGlowSubtraction for Siril) by Adrian Knagg-Baugh. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/GaiaGlowSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""AfterNight entry point for Gaia Glow Subtraction: runs the vendored pipeline and writes its result.

What the upstream ``finish_run`` and GUI do after a run is done here: the corrected image replaces the target in its
own sample type, the glow model can open as a new image, the measured PSF can be saved, and the output's fingerprint
is kept so that a second run on it is refused as a double subtraction.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import numpy as np

import afternight
from afternight import ui

import gaia_glow_subtraction_core as core
import gaia_glow_subtraction_io as ggs_io
import gaia_glow_subtraction_ui as ggs_ui


EXTENSION_ID = "gaia_glow_subtraction"
PASSES = ("auto", "1", "2")
CATALOGUE_SOURCES = ("auto", "local", "remote", "teff")


def _clip(value, low, high):
    return float(min(max(float(value), low), high))


def glow_params_from(params):
    """Build the core's GlowParams from native window values, within the upstream command line's ranges.

    The core's own glow-file option stays off: the glow model opens as an image instead of a file next to the input.
    """

    source = dict(params or {})
    defaults = core.GlowParams()
    psf_mode = str(source.get("psf_mode", "measure"))
    if psf_mode == "file":
        psf = str(source.get("psf_file") or "").strip()
        if not psf:
            raise ValueError("Gaia Glow Subtraction: choose the PSF file to load, or measure the PSF on the image.")
    else:
        psf = "measure"
    passes = str(source.get("passes", defaults.passes))
    catsource = str(source.get("catsource", defaults.catsource))
    if passes not in PASSES:
        raise ValueError(f"Gaia Glow Subtraction: unknown number of passes {passes!r}.")
    if catsource not in CATALOGUE_SOURCES:
        raise ValueError(f"Gaia Glow Subtraction: unknown catalogue source {catsource!r}.")
    maxdownload = (
        "auto"
        if bool(source.get("download_limit_auto", True))
        else _clip(source.get("download_limit_mb", 500.0), 0.0, 1e5)
    )
    return core.GlowParams(
        amount=_clip(source.get("amount", defaults.amount), 0.0, 1.0),
        psf=psf,
        savepsf=str(source.get("savepsf") or "").strip() if psf == "measure" else "",
        auto=bool(source.get("auto", defaults.auto)),
        faintG=_clip(source.get("faintG", defaults.faintG), 0.0, 16.0),
        tolerance=_clip(source.get("tolerance", defaults.tolerance), 0.0, 1.0),
        protect=_clip(source.get("protect", defaults.protect), 1e-4, 1.0),
        brightprotect=_clip(source.get("brightprotect", defaults.brightprotect), 0.0, 1.0),
        bgorder=int(_clip(source.get("bgorder", defaults.bgorder), 1, 3)),
        maxradius=_clip(source.get("maxradius", defaults.maxradius), 5.0, 90.0),
        passes=passes,
        maxdownload=maxdownload,
        glowimage=False,
        catsource=catsource,
        force=bool(source.get("force", defaults.force)),
        overwrite=bool(source.get("overwrite", defaults.overwrite)),
        offline_ok=bool(source.get("offline_ok", defaults.offline_ok)),
    )


def output_array(res_out, native_dtype, rescale):
    """The upstream ``output_array``, writing integer images back in their own sample type."""

    native_dtype = np.dtype(native_dtype)
    if native_dtype == np.uint16:
        return np.clip(np.rint(res_out * 65535.0), 0, 65535).astype(np.uint16)
    out = res_out.astype(np.float32, copy=False)
    if rescale != 1.0:
        out = out * np.float32(rescale)
    if np.issubdtype(native_dtype, np.integer):
        info = np.iinfo(native_dtype)
        return np.clip(np.rint(out), info.min, info.max).astype(native_dtype)
    return out


class HostRunContext(core.RunContext):
    """The core's RunContext without a dialog: soft refusals need Proceed Despite Warnings, and the host's cancel
    button ends the run at the core's next check."""

    def __init__(self, io, params, report, progress):
        super().__init__(io, params, report, ui=None)
        self._host_progress = progress

    def check_cancel(self):
        if self._host_progress is not None and self._host_progress.is_cancelled():
            self.cancel_event.set()
        super().check_cancel()


class GaiaGlowSubtractionExtension(ui.ProcessWindow):
    component = "extension.gaia_glow_subtraction"

    def get_params(self):
        return ggs_ui.parameter_defs()

    def get_settings_params(self):
        return ggs_ui.settings_defs()

    def on_process_launch(self):
        afternight.log_info(
            f"Gaia Glow Subtraction {core.VERSION}: AfterNight port of the Siril script by Adrian Knagg-Baugh. "
            "Use it on a linear, plate-solved, stacked image.",
            component=self.component,
        )

    def _log(self, message, kind="info"):
        if kind in ("warn", "error"):
            afternight.log_warning(str(message), component=self.component)
        else:
            afternight.log_info(str(message), component=self.component)

    def _settings_values(self):
        values = {}
        for item in ggs_ui.settings_defs():
            try:
                values[item["id"]] = self.settings.get(item["id"], item.get("default", ""))
            except Exception:
                values[item["id"]] = item.get("default", "")
        return values

    def _make_io(self, src_image, progress):
        return ggs_io.AfterNightIO(src_image, log_fn=self._log, progress=progress, settings=self._settings_values())

    def execute(
        self,
        target,
        src_image,
        dst_image,
        params,
        progress,
        masks=None,
        weights=None,
        output_masks=None,
    ):
        del target, masks, weights, output_masks
        glow_params = glow_params_from(params)
        io = self._make_io(src_image, progress)
        report = core.Report(self._log)
        subtractor = core.GlowSubtractor(io, glow_params, HostRunContext(io, glow_params, report, progress))
        try:
            result = subtractor.compute()
        except (core.HardRefusal, core.SoftRefusal) as exc:
            raise RuntimeError(f"Gaia Glow Subtraction: {exc}") from None
        except core.Cancelled as exc:
            raise RuntimeError(f"Gaia Glow Subtraction was cancelled: {exc}.") from None

        source = np.asarray(src_image.to_numpy())
        out = output_array(result.out, subtractor.native_dtype, subtractor.rescale)
        dst_image.from_numpy(ggs_io.from_planes(out, source))
        io.save_last_fingerprint(
            {
                "output": core.image_fingerprint(out, io.filename()),
                "amount": glow_params.amount,
                "label": result.label,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        dst_image.set_metadata("afternight.extension", EXTENSION_ID)
        dst_image.set_metadata(f"{EXTENSION_ID}.upstream_version", core.VERSION)
        dst_image.set_metadata(f"{EXTENSION_ID}.label", result.label)
        dst_image.set_metadata(f"{EXTENSION_ID}.attribution", ggs_ui.ATTRIBUTION_TEXT)

        if bool(dict(params or {}).get("glowimage", False)):
            glow = output_array(result.glow, np.float32, subtractor.rescale)
            ui.open_image(
                ggs_io.from_planes(glow, source),
                title="Gaia Glow Model",
                metadata={
                    "afternight.extension": EXTENSION_ID,
                    f"{EXTENSION_ID}.label": result.label,
                    f"{EXTENSION_ID}.attribution": ggs_ui.ATTRIBUTION_TEXT,
                },
            )
        self._save_psf(glow_params, result, report)
        report.info(f"Applied: {result.label}.")
        progress.set_value(100.0)

    @staticmethod
    def _save_psf(glow_params, result, report):
        """The upstream ``save_psf_file``, refusing to replace a file unless Overwrite is on."""

        path = glow_params.savepsf
        if not path or glow_params.psf != "measure" or not getattr(result, "psf_json", None):
            return
        if os.path.exists(path) and not glow_params.overwrite:
            report.warn(f"'{path}' exists and Overwrite the PSF File is off: the measured PSF was not saved.")
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(result.psf_json, handle, indent=1)
        report.info(f"Extended PSF saved as {path}")


__all__ = ["GaiaGlowSubtractionExtension"]
