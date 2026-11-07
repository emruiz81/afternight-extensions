# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Adrian Knagg-Baugh
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (GaiaGlowSubtraction for Siril) by Adrian Knagg-Baugh. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/GaiaGlowSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""Native process-window and settings schemas for Gaia Glow Subtraction.

The parameters, ranges and defaults are the upstream command line's (GlowParams and build_arg_parser).
"""

from __future__ import annotations

from afternight import ui

import gaia_glow_subtraction_core as core
import gaia_glow_subtraction_io as ggs_io


ATTRIBUTION_TEXT = (
    f"AfterNight port of GaiaGlowSubtraction {core.VERSION} for Siril by Adrian Knagg-Baugh, an independent "
    "reimplementation of PixInsight's PhotometricGlowSubtraction from its public documentation. Gaia DR3 data: "
    "ESA/Gaia/DPAC. AfterNight port by Ezequiel Ruiz."
)

DEFAULTS = core.GlowParams()


def _float(param_id, label, default, minimum, maximum, step, tooltip, **extra):
    param = {
        "id": param_id,
        "type": "float",
        "label": label,
        "default": float(default),
        "min": float(minimum),
        "max": float(maximum),
        "step": float(step),
        "tooltip": tooltip,
    }
    param.update(extra)
    return param


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[620, 860],
            resizable=True,
            preview_area=False,
            controls_panel_width=580,
            header_progress=True,
            target_selector=True,
            target_channel_filter=[1, 3],
        ),
        {"id": "attribution", "type": "info", "text": ATTRIBUTION_TEXT},
        {
            "id": "usage",
            "type": "info",
            "text": (
                "Subtracts the extended glow around bright stars from a linear, plate-solved, stacked image with its "
                "stars, before background extraction, colour calibration, deconvolution, star removal and "
                "stretching. Star fluxes come from Gaia DR3, downloaded once from the Siril catalogue mirror and "
                "cached (see the extension settings). A run can take a few minutes."
            ),
        },
        {"id": "subtraction", "type": "section", "label": "Subtraction"},
        _float(
            "amount",
            "Amount",
            DEFAULTS.amount,
            0.0,
            1.0,
            0.01,
            "How much of the glow model is subtracted. 1 subtracts the full model; lower values subtract less, never "
            "elsewhere.",
        ),
        _float(
            "tolerance",
            "Flux Tolerance (mag)",
            DEFAULTS.tolerance,
            0.0,
            1.0,
            0.01,
            "How far a star may be brightened from its Gaia value (mag). Useful 0-0.3. Higher values let the tool fit "
            "nebulosity as glow.",
        ),
        _float(
            "protect",
            "Core Protection",
            DEFAULTS.protect,
            0.0001,
            1.0,
            0.0001,
            "Brightness above which nothing is subtracted, protecting star cores. Recommended 0.001-0.01. Too low can "
            "carve dark rings into stars; too high leaves glow near bright stars.",
            decimals=4,
        ),
        _float(
            "brightprotect",
            "Bright-Star Protection",
            DEFAULTS.brightprotect,
            0.0,
            1.0,
            0.01,
            "How much of the brightness-dependent growth of the protection level is held back. 0 lets bright stars' "
            "protection grow up to 20x; 1 holds every star at the Core Protection level.",
        ),
        {"id": "stars", "type": "section", "label": "Stars and Model"},
        {
            "id": "auto",
            "type": "bool",
            "label": "Select Stars Automatically",
            "default": DEFAULTS.auto,
            "tooltip": "Select the stars whose glow is significant automatically. Untick to subtract all stars down "
            "to Faint G.",
        },
        _float(
            "faintG",
            "Faint G",
            DEFAULTS.faintG,
            0.0,
            16.0,
            0.1,
            "Faintest Gaia G magnitude subtracted when automatic star selection is off. Useful 6-11; faint limits are "
            "slow and subtract noise.",
            enabled_when={"param": "auto", "equals": False},
        ),
        _float(
            "maxradius",
            "Max Radius (arcmin)",
            DEFAULTS.maxradius,
            5.0,
            90.0,
            1.0,
            "Hard cap on the glow radius in arcmin. Useful 20-60; large values are slower and need a larger "
            "catalogue cone.",
        ),
        {
            "id": "bgorder",
            "type": "int",
            "label": "Background Order",
            "default": DEFAULTS.bgorder,
            "min": 1,
            "max": 3,
            "step": 1,
            "tooltip": "Polynomial order of the background in the joint fit. 2 suits most images; 3 for strong "
            "gradients, at some risk of absorbing glow.",
        },
        {
            "id": "passes",
            "type": "choice",
            "label": "Passes",
            "default": DEFAULTS.passes,
            "options": [["Automatic", "auto"], ["1", "1"], ["2", "2"]],
            "tooltip": "Measurement passes. Automatic uses 2 when bright stars' glows overlap.",
        },
        {"id": "psf_section", "type": "section", "label": "Extended PSF"},
        {
            "id": "psf_mode",
            "type": "choice",
            "label": "Extended PSF",
            "default": "measure",
            "options": [["Measure on this image", "measure"], ["Load from a file", "file"]],
            "tooltip": (
                "Measure: measure the extended PSF on the whole image. File: load a PSF saved from a clean field. In "
                "nebula-dominated fields the measured PSF takes nebulosity for glow; use one from a nebula-free field "
                "taken with the same telescope, camera and filter."
            ),
        },
        {
            "id": "psf_file",
            "type": "string",
            "label": "PSF File",
            "default": "",
            "enabled_when": {"param": "psf_mode", "equals": "file"},
            "tooltip": "Extended PSF file (.ggspsf) saved by Gaia Glow Subtraction or by the Siril script.",
        },
        {
            "id": "savepsf",
            "type": "string",
            "label": "Save Measured PSF To",
            "default": "",
            "enabled_when": {"param": "psf_mode", "equals": "measure"},
            "tooltip": "Save the measured extended PSF (.ggspsf), e.g. from a clean field, to load it later for "
            "nebula-dominated fields.",
        },
        {"id": "outputs", "type": "section", "label": "Outputs"},
        {
            "id": "glowimage",
            "type": "bool",
            "label": "Open the Glow Model",
            "default": DEFAULTS.glowimage,
            "tooltip": "Also open the subtracted glow as a new image.",
        },
        {
            "id": "overwrite",
            "type": "bool",
            "label": "Overwrite the PSF File",
            "default": DEFAULTS.overwrite,
            "tooltip": "Allow Save Measured PSF To to replace an existing file.",
        },
        {"id": "catalogue", "type": "section", "label": "Catalogue and Checks"},
        {
            "id": "download_limit_auto",
            "type": "bool",
            "label": "Automatic Download Limit",
            "default": True,
            "tooltip": "Allow the catalogue download the field needs, up to an automatic limit.",
        },
        _float(
            "download_limit_mb",
            "Download Limit (MB)",
            500.0,
            0.0,
            100000.0,
            10.0,
            "Largest catalogue download allowed for one run.",
            enabled_when={"param": "download_limit_auto", "equals": False},
        ),
        {
            "id": "catsource",
            "type": "choice",
            "label": "Catalogue Source",
            "default": DEFAULTS.catsource,
            "options": [
                ["Automatic", "auto"],
                ["Local Siril catalogues only (testing)", "local"],
                ["Remote catalogue only (testing)", "remote"],
                ["Temperatures instead of spectra (testing)", "teff"],
            ],
            "tooltip": "Testing only: override the colour source priority (local XP, remote XP, Teff, default).",
        },
        {
            "id": "offline_ok",
            "type": "bool",
            "label": "Continue Without a Catalogue",
            "default": DEFAULTS.offline_ok,
            "tooltip": "When no catalogue is reachable, model the glow of stars inside the frame only.",
        },
        {
            "id": "force",
            "type": "bool",
            "label": "Proceed Despite Warnings",
            "default": DEFAULTS.force,
            "tooltip": (
                "Run even after a soft refusal, such as a glow subtraction already applied to this image or very "
                "elongated stars. The log says what was overridden."
            ),
        },
    ]


def settings_defs():
    return [
        {
            "id": "data_dir",
            "type": "dir_path",
            "label": "Catalogue Cache Folder",
            "default": "",
            "group": "Catalogue",
            "tooltip": (
                "Where downloaded Gaia catalogue pieces and the bright-star table are cached. Empty uses "
                f"{ggs_io.default_data_dir()}. Siril's user data folder can be chosen to share its cache."
            ),
        },
        {
            "id": "siril_astro_catalogue",
            "type": "file_path",
            "label": "Siril Astrometric Catalogue",
            "default": "",
            "group": "Catalogue",
            "tooltip": "Optional local Siril Gaia astrometric catalogue file; without it positions come from the XP data.",
        },
        {
            "id": "siril_xp_catalogue_dir",
            "type": "dir_path",
            "label": "Siril XP Catalogue Folder",
            "default": "",
            "group": "Catalogue",
            "tooltip": "Optional folder of Siril's local Gaia XP catalogue chunks; without it they are downloaded.",
        },
    ]
