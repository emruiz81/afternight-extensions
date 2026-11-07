# SPDX-License-Identifier: GPL-3.0-or-later
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (GaiaGlowSubtraction for Siril) by Adrian Knagg-Baugh. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/GaiaGlowSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.
#
# Below the marker line is the upstream script's numerical core, lines 1-7400 (sections 0 to 13), unchanged apart
# from its sirilpy import block (upstream lines 122-127). gaia_glow_subtraction_io.py replaces section 14 (the Siril
# I/O adapter) and the native process window replaces sections 15 and 16. Refresh this file from upstream rather
# than editing it: test_gaia_glow_subtraction_vendor.py holds it to the upstream text.
# --- vendored upstream text below ---
# (c) Adrian Knagg-Baugh 2026
# GaiaGlowSubtraction: photometric subtraction of bright-star glow
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Contact: aje.baugh@gmail.com, or open an issue on
# https://gitlab.com/free-astro/siril-scripts

"""
GaiaGlowSubtraction subtracts a physical model of the extended glow
(scattering aureole) around bright stars:

    glow_i(x) = F_i * p(|x - x_i|)

F_i is the star's flux in the image's photometric system, predicted from
Gaia DR3 (G plus the XP sampled spectrum, or Teff) through a zero point
calibrated on the image's own unsaturated stars. Stars brighter than G = 4,
where Gaia is incomplete and its XP photometry unreliable, take their flux
from a Hipparcos table (V, B-V, V-I; fetched from VizieR once and cached)
through a colour relation fitted on the field's own XP stars. p is an empirical
extended PSF measured from the image itself, per unit calibrated flux.
The model is not fitted to the pixels around each star (apart from a
small flux refinement and a cap at the light actually present), so faint
structure lying under the glow is not part of the model and survives.

This is an independent reimplementation of the functionality of the
PixInsight tool PhotometricGlowSubtraction (deepskycolors.com), based
only on its public documentation. Differences are marked "PGS
difference" in the code.

Workflow position: stack -> plate solve -> glow subtraction ->
background extraction -> colour calibration -> deconvolution / star
removal / stretching. The tool needs a linear, plate-solved, stacked
image with its stars.

It does not remove gradients, noise, halos or reflections, diffraction
spikes or star cores.

CLI usage (Siril console or script):
    pyscript GaiaGlowSubtraction.py [-amount=1.0] [-psf=measure|selection|file]
        [-savepsf=file] [-auto[=on|off]] [-faintG=9] [-tolerance=0.3]
        [-protect=0.01] [-brightprotect=0.5] [-bgorder=2]
        [-maxradius=43] [-passes=auto|1|2] [-maxdownload=auto|MB]
        [-glowimage] [-catsource=auto|local|remote|teff]
        [-force] [-overwrite] [-offline-ok]

The script file is organised in numbered sections:
     0  header, constants and tunable thresholds
     1  parameters (GlowParams) and argparse
     2  generic numerical helpers
     3  catalogue access (HEALPix files, local/remote XP, Siril cache,
        bright-star table, query plan)
     4  synthetic photometry
     5  image geometry (WCS, conventions, detections, astrometric check)
     6  joint background + outer-wing fit
     7  photometric calibration
     8  model rendering (two-resolution) and radial ring measurement
     9  extended PSF (combination, extension, chromaticity, save/load)
    10  star selection and flux refinement
    11  glow rendering, own-light cap, core protection
    12  misuse checks (section 15 of the design spec)
    13  orchestration (GlowSubtractor) and report
    14  Siril I/O adapter (sirilpy)
    15  PyQt6 GUI
    16  CLI main()

The numerical core (sections 2-13) does not talk to Siril directly: it
goes through the adapter in section 14, so it can be exercised
standalone.
"""

# Version history
VERSION = "1.2.6"
# 1.0.0: AKB - initial release (design spec draft 3.2, CDR)
# 1.0.1: AKB - smooth ePSF profile (no fixed-radius circles); GUI worker thread lifecycle fix
# 1.1.0: AKB - GUI result preview and actions, automatic download limit, PSF from a selection
# 1.1.1: AKB - core protection for every caster whose core touches the frame; pixel-wise
#              safety net on the subtraction; GUI progress from the run, cached border check
# 1.1.2: AKB - ePSF: tail slope and hand-over from the azimuthal median, honest sector ring
#              errors, switchable profile safety rule (PROFILE_SAFETY)
# 1.1.3: AKB - no-dip test on the modelled rings only, residual profile over all valid pixels,
#              untouched outer level removed (far glow was given back on nebula fields)
# 1.2.0: AKB - bright stars (V < 3.5) from an embedded Hipparcos table instead of stars.csv; their
#              flux from V, B-V, V-I through a colour relation fitted on the field's XP stars;
#              per-channel flux refinement within a prior built from the error budget
# 1.2.1: AKB - bright-star table (V < 4.2) fetched from VizieR at run time and cached in the
#              user data directory instead of embedded; runs without it if it cannot be built
# 1.2.2: AKB - saturated, off-frame and route-B casters the rings cannot refine at a lower bound of
#              their prediction (2 sigma of their error budget), applied as a final reduction
# 1.2.3: AKB - faster and leaner, same output: grouped ring/sector medians, per-caster boxes in the
#              joint fit, patches cut to each star's extent, banded clamp filters, cached
#              background, earlier release of models and caches; memory estimate fitted to the peak
# 1.2.4: AKB - no dark lanes: where a star's glow is bright its ring values are bounded by the
#              azimuthal floor (noise-corrected minimum of 3-degree bins), and a lane guard cuts
#              each caster's model radially wherever the floor of the residual falls below the
#              background (before and after the clamp); the fingerprint check fetches only its rows
# 1.2.5: AKB - sigma_bg capped by the pixel-difference noise (galaxy structure had inflated it
#              up to 6x on crops); bright casters' inner profile from their own ring floor; lane
#              guard against the local sky, with no allowance and a tapered edge
# 1.2.6: AKB - amount is a plain factor on the safe glow computed at amount 1 (it can only give
#              light back); the GUI computes at 1 and follows the amount box without a re-run;
#              a second Apply needs an Undo first

import sys
import os

import re
import csv
import json
import math
import time
import struct
import sqlite3
import argparse
from io import StringIO
import tempfile
import threading
import traceback
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime, timezone
from pathlib import Path

# AfterNight port: upstream lines 122-127 imported sirilpy (SirilInterface, LogColor, parse_fits_header) and
# called s.ensure_installed(); the package's requirements.lock provides the dependencies and
# gaia_glow_subtraction_io.py replaces the Siril I/O adapter.

import numpy as np
from scipy import ndimage
from scipy.optimize import lsq_linear
from scipy.spatial import cKDTree
from scipy.special import ndtri

# PyQt6 and the network/astro libraries are imported lazily where they are
# used, so that the numerical core can be imported without a display.

# ===========================================================================
# 0. Constants and tunable thresholds
# ===========================================================================

SIRILPY_REQUIRED = ">=1.0.25"
LABEL_PREFIX = "GaiaGlowSub"

# --- Catalogue formats (spec 4.1) -----------------------------------------
HEADER_SIZE = 128
HEADER_STRUCT = "<48s5B3I63s"
CAT_ASTRO, CAT_XPSAMP, CAT_XPCTS = 1, 2, 3
HP_LEVEL = 8
HP_NSIDE = 1 << HP_LEVEL
N_INDEX_ASTRO = 12 * 4 ** HP_LEVEL           # 786432
CHUNK_LEVEL = 1
N_INDEX_CHUNK = 4 ** (HP_LEVEL - CHUNK_LEVEL)  # 16384
N_CHUNKS = 12 * 4 ** CHUNK_LEVEL               # 48
REC_ASTRO = 16
REC_XP = 701
AUTO_DOWNLOAD_FLOOR_MB = 50.0
XP_NWL = 343
XP_WL = 336.0 + 2.0 * np.arange(XP_NWL)       # nm
XP_G_MAX = 15.0
COORD_SCALE = 360.0 / 2147483647.0            # int32 -> degrees
GAIA_EPOCH = 2016.0
G_KEEP_MAX = 17.5          # fainter Gaia stars are dropped after reading
G_NEIGHBOUR_MASK = 14.0    # Gaia stars masked as neighbour cores
XP_FILE_TEMPLATE = "siril_cat1_healpix8_xpsamp_{c}.dat"
REMOTE_MIRRORS = ["https://zenodo.org/records/17988559/files"]
HTTP_TIMEOUT = 30.0
HTTP_RETRIES = 3
CACHE_BATCH = 64
JOIN_MIN_FRACTION = 0.90
JOIN_NN_ARCSEC = 0.2
JOIN_NN_DG = 0.02

ASTRO_DTYPE = np.dtype([("ra", "<i4"), ("dec", "<i4"), ("pmra", "<i2"),
                        ("pmdec", "<i2"), ("teff", "<u2"), ("g", "<i2")])
XP_DTYPE = np.dtype([("ra", "<i4"), ("dec", "<i4"), ("pmra", "<i2"),
                     ("pmdec", "<i2"), ("g", "<i2"), ("fexpo", "u1"),
                     ("flux", "<f2", (XP_NWL,))])
assert ASTRO_DTYPE.itemsize == REC_ASTRO and XP_DTYPE.itemsize == REC_XP

# --- Geometry (spec 5) ----------------------------------------------------
BORDER_BAND = 0.05
MATCH_RADIUS_PX = 3.0
OFFSET_APPLY_PX = 0.3
LIN_FRACTION = 0.9

# --- Joint fit (spec 6) ---------------------------------------------------
BLOCK_TARGET = 256
BLOCK_MIN_VALID = 0.5
ALPHA0 = 2.5
N_WING_BASES = 10
PRUNE_THRESHOLD = 0.1      # residual/original norm below which an annulus is dropped
RIDGE_FRACTION = 0.01      # ridge weight as a fraction of trace(normal matrix)
TUKEY_C = 4.685
TUKEY_ITER = 3
INNER_MASK_SIGMA = 0.1     # inner-zone mask threshold, in sigma_bg^(0)
CORE_MASK_FWHM = 3.0
BASIS_REL_ERR_MAX = 0.5

# --- Photometry (spec 7) --------------------------------------------------
AP_FWHM = 3.0
EDGE_FWHM = 10.0
SNR_MIN = 30.0
SNR_SLOPE = 100.0
ETA = 2.0                  # correlated-noise factor of registered stacks
ETA_DRIZZLE = 3.0
NEIGHBOUR_DMAG = 2.5
NEIGHBOUR_FWHM = 6.0
HUBER_K = 1.345
CLIP_SIGMA = 3.0
SIGMA_AGREE_WARN = 0.20
SIGMA_AGREE_ABORT = 0.35   # spec 14 Q11: kept at 0.35 until the first H-alpha test
MIN_CAL_STARS = 15

# --- Rings and ePSF (spec 8) ----------------------------------------------
RING_NATIVE_PX = 50.0
RING_DLNR = 0.08
RING_MIN_N = 20
RING_MIN_COVERAGE = 0.10
RING_MAX_SAT_FRAC = 0.005
RING_MAX_SAT_FRAC_FAR = 0.05
MAX_RING_STARS = 3000
COARSE_MAX_PIX = 4.0e6
MIN_STARS_RING = 5
MIN_STARS_FAR = 1           # beyond FAR_FWHM: sector-checked rings of 1+ stars suffice
FAR_FWHM = 10.0
MAX_GAP_FACTOR = 3.0        # the reach walk skips undefined rings over at most this factor in r
SECTOR_MIN_FWHM = 4.0       # rings beyond this use sector-robust values
N_SECTORS = 8
SECTOR_QUANTILE = 25.0      # ring value = this percentile of the sector medians (conservative)
SECTOR_MIN_VALID = 3
ALPHA_MIN_TAIL = 1.2
CONSERVATIVE_SIGMA = 0.5    # profile lowered by this many sigma beyond 4 FWHM (PROFILE_SAFETY "quantile")
SECTOR_NOISE_FACTOR = 1.2   # SPEC (round 12): a sector-based ring value is this much noisier than the ring median
# SPEC (round 12): how the ring value that renders the model errs low beyond 4 FWHM.
#   "quantile":   the SECTOR_QUANTILE percentile of the sector medians, and the combined
#                 profile is lowered by CONSERVATIVE_SIGMA of its error (rounds 3-11).
#   "lowerbound": the azimuthal median minus PROFILE_LB_Z times the azimuthal scatter in
#                 excess of the noise; no further shift. One stated choice: the model is the
#                 one-sided bound that 1 - Phi(-z) = 75% of the azimuth lies above when
#                 the sectors disagree, and the unbiased median when they agree within noise.
PROFILE_SAFETY = "lowerbound"   # round 12 A/B on M31, bubble, Alnitak: "quantile" with the honest errors
                                # removed less at 50-105 px than round 11; "lowerbound" removed more with
                                # the same sector minima
PROFILE_LB_Z = 0.6745
# SPEC (round 19): azimuthal floor of the rings. A bright star's ring pattern is a dim floor
# with bright lanes (mirror-clip diffraction, a few degrees wide) on top. The lanes are
# instrument artefacts the symmetric model does not try to remove, but they lift the ring
# median, and they lift all eight 45-degree sectors alike, so the sector scatter of the
# lower-bound rule does not see them: the model was sized between the floor and the lanes,
# and the floor came out at or below the background as dark lanes (M31, G = 4.49 star at
# 25-130 px). Beyond the sector blend the ring value is therefore also bounded by the
# floor: the FLOOR_QUANTILE percentile of the medians of FLOOR_BINS azimuthal bins
# (3 degrees; merged to coarser bins where a ring holds fewer than FLOOR_MIN_N samples per
# bin), corrected for its noise bias with the measured noise of a bin median. With
# FLOOR_QUANTILE = 0 it is the minimum over the azimuth: no part of the ring is expected
# to lie below the model (no-undershoot rule; 1% and 5% left the floor bins of the M31
# star at 50-130 px 0.3-0.5 sigma lower, A/B round 19).
FLOOR_BINS = 120
FLOOR_BIN_COUNTS = (8, 10, 12, 15, 20, 24, 30, 40, 60, 120)   # divisors of FLOOR_BINS
FLOOR_MIN_N = 4             # samples per bin (pixels, or block-median cells beyond 50 px)
FLOOR_MIN_BINS = 8
FLOOR_GLOW_SIGMA = (1.0, 3.0)   # the floor is blended in where the star's own model rises over
                                # this range (sigma_bg); beyond 50 px it is measured on the native
FLOOR_NATIVE_MAX_PX = 400.0     # pixels from the lower value on, out to this radius
FLOOR_QUANTILE = 0.0
FLOOR_SIG = (1.0, 3.0)      # the floor's deficit (in its sd) over which it replaces the ring value
FLOOR_START_FWHM = (2.0, 3.0)   # radius (FWHM) over which the floor is blended in
SHAPE_SMOOTH_DLNR = 0.1         # SPEC (round 20): smoothing (ln r) of the per-star inner shape
SHAPE_GLOW_SIGMA = (3.0, 10.0)  # SPEC (round 20): the shape is blended in where the star's own model rises over this (sigma_bg)
PROFILE_SMOOTH_DLNR = 0.12  # SPEC (round 4): Gaussian sigma (in ln r) of the ePSF profile smoothing
PROFILE_SMOOTH_FWHM = (2.0, 3.5)  # raw profile inside the first, smoothed beyond the second (FWHM)
PROFILE_FINE_DLNR = 0.02    # the smoothed profile is tabulated on this ln r step
CLAMP_SMOOTH_PX = 3.0       # Gaussian sigma (px) of the local-light estimate for the final clamp
CLAMP_PERCENTILE = 25.0
CLAMP_PCT_BIAS = 0.5        # sigma added back to the 25th percentile (white-noise value 0.6745)
CLAMP_STEEP_SIGMA = (10.0, 30.0)  # requested glow (sigma) over which the min-filter branch blends in
CLAMP_MEDIAN_PX = 5         # sliding median size of the robust clamp branch
CLAMP_K = 0.5               # noise allowance of the clamp, in sigma of that estimate
CLAMP_NET_K = 5.0           # pixel-wise safety net, in sigma of the local (shot) noise
CLAMP_BG_SIGMA_BLOCKS = 4.0 # smoothing (blocks) of the glow-free background residual
CLAMP_BAND = 1024           # SPEC (round 18): the clamp filters run on bands of this many rows ...
CLAMP_HALO = 32             # ... with this margin (px; the filter chain reaches 24 px)
REFIT_AMP_RANGE = (0.8, 1.25) # a refit is kept only if the template amplitude is consistent
N_TEMPLATE_REFITS = 0       # joint-background refits with the measured ePSF as wing template
NODIP_MAX_STARS = 400        # brightest casters checked for a radial dip (dark ring)
NODIP_RINGS = 40
NODIP_MIN_SIGMA = 0.05       # dips smaller than this (sigma) are noise
NODIP_ROWS = 256             # SPEC (round 18): rows per band of the add-back evaluation
# SPEC (round 19): lane guard (floor_guard), on the request before the clamp and on the
# output after it. Around every in-frame caster whose subtracted glow at its protection
# disc is GUARD_MIN_SIGMA or more, the residual's azimuthal floor (the noise-corrected
# minimum of fine azimuth bins, as for the rings) is measured in narrow radial bands on
# native pixels, out to where the star's own subtracted glow falls to GUARD_END_SIGMA
# (fainter, a lane is a fraction of a sigma deep and the floor follows the sky's own
# structure); where it lies below the reference (the background, or the input's own floor
# where that is lower) by more than GUARD_Z times its noise, the missing amount is taken
# off this star's own subtraction, radially (the model stays symmetric).
GUARD_MIN_SIGMA = 2.0
GUARD_END_SIGMA = 2.0
GUARD_DR_PX = 0.75           # band width: max(GUARD_DR_PX, GUARD_DLNR r)
GUARD_DLNR = 0.1
GUARD_Z = 0.0                # SPEC (round 20): was 1 (sd of the floor)
GUARD_MARGIN = 1.0
MEDIAN_EFF_INV = 1.0 / 1.2533
GUARD_MAX_PX = 400.0
GUARD_TAPER = 0.3            # SPEC (round 20): outer fraction of the guarded radius over which the give-back ends
GUARD_MAX_STARS = 3000
NOISE_LAG_PX = 3             # SPEC (round 20): sigma_bg from pixel differences at this lag ...
NOISE_LAG_CAP = 1.25         # ... caps the residual MAD at this multiple of it
UNDERSHOOT_Z = 3.0          # internal check: sector median below -3 sigma(median) = undershoot
RING_REJECT_SIGMA = 4.0
OVERLAP_WARN = (0.85, 1.15)
MEDIAN_EFF = 1.2533
PSF_FILE_VERSION = 1

# --- Selection, refinement, rendering, protection (spec 9) ----------------
RGLOW_SIGMA = 0.02         # SPEC (round 3): modelling radius; was 0.1 (Q9), tails were visible beyond it
SELECT_SIGMA = 0.1         # selection keeps the spec's 0.1 sigma rule (R > 4 FWHM), Q9
GEN_WING_AMP = 1e-4
SELECT_FWHM = 4.0
NEIGHBOUR_MODEL_MAX = 0.5
NEIGHBOUR_DOM_FACTOR = 3.0  # ePSF: drop a star's ring where the others' model exceeds 3x its own
REFINE_DIM_MAX = 0.3
REFINE_MAX_SIGMA_S = 0.1    # refine only if the rings constrain s to better than this
# SPEC (round 17): a saturated, off-frame or route-B caster whose flux the rings cannot
# refine (off frame, sigma_s above REFINE_MAX_SIGMA_S, or fewer than 5 usable rings) is
# rendered at a lower bound of its prediction, F_pred 10^(-0.4 min(UNREF_K sigma,
# REFINE_DIM_MAX)), and at the dimmer of two valid routes; the bound stays inside the
# range the refinement itself could reach [-REFINE_DIM_MAX, +bright bound].
# sigma: route B its prior (round 15); XP sigma_agree with
# UNREF_SIG_XP; Teff / no colour sigma_agree with UNREF_SIG_TEFF.
UNREF_K = 2.0               # one-sided 97.7% bound, the same K as the route-B bright bound
UNREF_SIG_XP = (4.0, 0.04, 0.01)   # XP vs Hipparcos V (all-sky): 0.04 mag MAD at G < 4, else 0.01
UNREF_SIG_TEFF = 0.15       # Teff route vs XP (all-sky): MAD up to 0.15 mag
ALT_ROUTE_GMIN = 3.0        # XP is a valid second route for a route-B star only at G >= 3
INNER_ZONE_CELLS = 16
CAP_K = 1.0
PROTECT_GROWTH_MAX = 20.0
PROTECT_GROWTH_DIV = 5.0

# --- Misuse checks (spec 15) ----------------------------------------------
I3_MIN_MATCHES = 10
I3_MIN_FRACTION = 0.20
I3_DET_AREA_MIN = 0.25      # SPEC (round 8): detections spanning less of the frame -> "sub-region" message
I3_MAX_RMS = 2.0
I3_WARN_RMS = 1.0
ASTROM_SIP_OK_RMS = 0.5     # px: SIP residual above this triggers the internal correction
LINEAR_WCS_MSG = ("The plate solution is linear only (no SIP distortion terms). Re-solve in Siril "
                  "with a polynomial (distortion) order of 2 or more for best results; an internal "
                  "correction fitted on the image's stars is used instead.")
MERGE_FWHM = 2.0            # stars closer than max(2 FWHM, MERGE_ARCSEC) are one caster
MERGE_ARCSEC = 4.0
INNER_CAP_SIZE = 5          # px: median filter of the light for the inner-zone cap
HANDOVER_L = 0.3            # ln-r relaxation length of the r_meas hand-over
I4_SOFT = (0.85, 1.15)
I4_WARN = (0.95, 1.05)
I4_MIN_SPAN = 3.0
I5_HISTORY = ("background extraction", "subsky", "graxpert", "background")
I5_SIGMA = 3.0
I5_MIN_LOG_OFFSET = 0.3     # tuning addition: also require ln(p_meas/p_joint) > 0.3
I6_DET_FRACTION = 0.10
I6_CORE_SIGMA = 5.0
I7_SIGMA = 5.0
I7_REL = 0.02
I8_CAL_TYPES = ("dark", "flat", "bias", "offset")
I8_SINGLE_EXP = 120.0
I9_EXTS = ("jpg", "jpeg", "png", "bmp", "gif", "webp")
I10_MAX = 1.5
I11_ZERO_FRAC = 0.01
I12_SCALE_RATIO = 0.5
I13_WARN, I13_SOFT = 0.75, 0.5
I14_HISTORY = ("deconvolution", "rl", "wiener", "starnet", "blurx")
I17_WARN_DEG, I17_SOFT_DEG = 5.0, 15.0
I17_OFF_FRACTION = 0.25
I18_RES_SIGMA = 3.0
SEL_MIN_STARS = 5           # SPEC (round 5): -psf=selection needs this many measured stars inside
SEL_MIN_REACH_FWHM = 4.0    # ... and a measured reach of at least this (else refused)
SEL_WARN_REACH_FWHM = 10.0  # ... below this the far wing is the conservative tail (warned)
I18_FRACTION = 0.25
STRETCH_HISTORY = ("ght", "asinh", "mtf", "autostretch", "modasinh")
SCALE_WARN_ARCSEC = 6.0
P2_LOW = 0.0005
P2_PROTECTED = 0.9
P3_TOL = 0.5
P4_MAX_STARS = 2000
R5_SOFT, R5_WARN = 0.8, 0.5
OVERSUB_SIGMA = 3.0
OVERSUB_GLOW = 0.5
OVERSUB_CTRL = 0.1

NB_DEFAULT_BW = 6.0
NB_LINES = {"ha": 656.28, "h-alpha": 656.28, "halpha": 656.28,
            "oiii": 500.7, "o3": 500.7, "sii": 672.4, "s2": 672.4,
            "hb": 486.1, "hbeta": 486.1, "nii": 658.4}

# --- Bright-star table (source D) and route B (SPEC round 15) --------------
# SPEC (round 15): source D is a Hipparcos table (round 16: built at run time, see
# BRIGHT_VMAX); Siril's stars.csv no longer supplies stars. Gaia DR3 lacks about 20% of the
# stars brighter than G = 3 (and Polaris); from V = 3.5 to 5 it lacked 2 of 1320 Hipparcos
# stars in an all-sky check, the same rate as for fainter stars.
# Route B: a table star's channel fluxes come from its Hipparcos V, B-V and V-I through a
# colour relation fitted on the field's own Gaia XP stars (synthetic Johnson V, B and
# Cousins I from their XP spectra). All-sky validation on 18,760 Hipparcos stars: route B
# agrees with XP synthetic photometry to 0.02 mag (0.007-0.016 MAD) at G 4-9, while XP
# itself is off by -0.03 +- 0.04 mag in V at G 3-4 and by -0.35 mag at G < 3; the Teff
# route (B-V -> Teff -> kappa) is biased by +0.06 (G) to +0.28 mag (B) with 0.05-0.15 MAD.
HIP_EPOCH = 1991.25            # Hipparcos positions: ICRS at epoch J1991.25
HIP_ROUTE_GMAX = 4.0           # Gaia stars brighter than this with a table entry use route B
HIP_COMBINED_ARCSEC = 10.0     # Gaia stars this close to a route-B star are in its combined light
HIP_COMBINED_DMAG = 5.0        # ... if they are within this many magnitudes of it
HIP_REL_GMIN = 6.0             # XP stars fainter than this calibrate the colour relation
HIP_REL_MIN_STARS = 50
HIP_V_ERR = 0.015              # hip_main gives no V error; ground-based V of bright stars
HIP_SYS = 0.025                # route B - XP systematics (all-sky, per channel, blue stars)
HIP_EXTRAP = 0.03              # mag per mag of B-V outside the calibrators' 2-98% range
HIP_MULT_ERR = 0.05            # Hipparcos MultFlag set: combined vs resolved light (all-sky MAD 0.065)
HIP_PRIOR_K = 2.0              # route-B refinement bound = K sigma_prior ...
HIP_PRIOR_MIN = 0.05           # ... but at least this (mag)
# Bessell (1990, PASP 102, 1181) Table 2 passbands B, V (Johnson) and I (Cousins) as in
# Siril's SPCC database (Johnson_photometric.json): first wavelength (nm), 10 nm steps.
BESSELL_BVI = {
    "B": (360, (0, .03, .134, .567, .92, .978, 1, .978, .935, .853, .74, .64, .536, .424, .325,
                .235, .15, .095, .043, .009, 0)),
    "V": (470, (0, .03, .163, .458, .78, .967, 1, .973, .898, .792, .684, .574, .461, .359, .27,
                .197, .135, .081, .045, .025, .017, .013, .009, 0)),
    "I": (700, (0, .024, .232, .555, .785, .91, .965, .985, .99, .995, 1, 1, .99, .98, .95, .91,
                .86, .75, .56, .33, .15, .03, 0)),
}
# Synthetic photometry: energy integration (sum f_lambda T) against the AB spectrum, then
# Hipparcos - synthetic = c2 b^2 + c1 b + c0 with b the synthetic B-V, fitted on 7,272 single,
# constant Hipparcos stars with 6.5 < V < 8.5 (residual MAD 0.007 V, 0.013 B-V, 0.027 V-I).
JC_STANDARD = {"V": (0.0056, -0.0143, 0.0171), "B-V": (-0.0153, 0.0038, 0.1506),
               "V-I": (-0.0285, -0.0075, 0.4110)}
# SPEC (round 16): the bright-star table (source D) is no longer embedded. It is built at
# run time from a read-only VizieR TAP query of the Hipparcos main catalogue (ESA 1997,
# ESA SP-1200; VizieR I/239/hip_main), every entry with Vmag < BRIGHT_VMAX, and cached as a
# plain CSV in <userdatadir>/gaiaglowsubtraction/. V < 4.2 matches the G = 4 hand-over
# (HIP_ROUTE_GMAX). Positions are ICRS at epoch J1991.25 (HIP_EPOCH); names from Siril's
# stars.csv when it is installed (logs only).
BRIGHT_VMAX = 4.2
BRIGHT_FORMAT = 1               # cache file format; a different version is rebuilt
BRIGHT_FILE = "hipparcos_bright.csv"
BRIGHT_TAP_URL = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
BRIGHT_QUERY = ('SELECT HIP, RAICRS, DEICRS, pmRA, pmDE, Vmag, VarFlag, "B-V", "e_B-V", "V-I", '
                '"e_V-I", Hpmax, HPmin, MultFlag, Ncomp, rho, dHp '
                f'FROM "I/239/hip_main" WHERE Vmag < {BRIGHT_VMAX} ORDER BY HIP')
BRIGHT_TIMEOUT = 20.0           # s per attempt (2 attempts); the answer is about 60 kB
BRIGHT_MAX_BYTES = 2 * 1024 * 1024
BRIGHT_ROWS = (550, 700)        # plausible row count for V < 4.2 (624 on 2026-10-25)
BRIGHT_COLUMNS = ("hip", "ra", "dec", "pmra", "pmdec", "vmag", "bv", "ebv", "vi", "evi",
                  "var", "amp", "mult", "ncomp", "rho", "dhp", "name")
D_MATCH_ARCSEC = 15.0
D_MATCH_DMAG = 1.5


# ===========================================================================
# 1. Parameters and argument parsing
# ===========================================================================

@dataclass
class GlowParams:
    """User parameters (spec 3). Defaults are the spec defaults."""
    amount: float = 1.0
    psf: str = "measure"
    savepsf: str = ""
    auto: bool = True
    faintG: float = 9.0
    tolerance: float = 0.30
    protect: float = 0.01
    brightprotect: float = 0.5
    bgorder: int = 2
    maxradius: float = 43.0          # arcmin
    passes: str = "auto"             # "auto" | "1" | "2"
    maxdownload: object = "auto"     # "auto" or MB (SPEC round 5)
    glowimage: bool = False
    catsource: str = "auto"          # auto | local | remote | teff
    force: bool = False
    overwrite: bool = False
    offline_ok: bool = False

    def label(self):
        """Undo label / HISTORY record, at most 70 bytes (spec 9.5)."""
        psf = {"measure": "meas", "selection": "sel"}.get(self.psf, "file")
        lab = (f"{LABEL_PREFIX} v{VERSION[:3]} a={self.amount:.2f} "
               f"T={self.protect:.4f} b={self.brightprotect:.2f} "
               f"tol={self.tolerance:.2f} R={self.maxradius:.0f} psf={psf}")
        return lab.encode("utf-8")[:70].decode("utf-8", "ignore")

    def full_text(self):
        d = asdict(self)
        return "GaiaGlowSubtraction v%s parameters: %s" % (
            VERSION, ", ".join(f"{k}={v}" for k, v in d.items()))


class ArgumentError(Exception):
    """Raised for invalid command-line arguments (spec 15.2 P1)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)

    def exit(self, status=0, message=None):
        if message:
            raise ArgumentError(message)
        raise ArgumentError("help requested")


def _bool_arg(v):
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in ("1", "on", "yes", "true", "y", "t"):
        return True
    if t in ("0", "off", "no", "false", "n", "f"):
        return False
    raise argparse.ArgumentTypeError(f"expected on/off, got '{v}'")


def _ranged(name, lo, hi, default, kind=float, log_hint=""):
    def conv(v):
        try:
            x = kind(v)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"-{name}: '{v}' is not a number (allowed {lo}-{hi}, "
                f"default {default})")
        if not (lo <= x <= hi) or (isinstance(x, float) and not math.isfinite(x)):
            raise argparse.ArgumentTypeError(
                f"-{name}={v} is out of range: allowed {lo}-{hi}, "
                f"default {default}{log_hint}")
        return x
    return conv


def _download_arg(v):
    t = str(v).strip().lower()
    if t == "auto":
        return "auto"
    conv = _ranged("maxdownload", 0.0, 1e5, "auto")
    try:
        return conv(t)
    except argparse.ArgumentTypeError:
        raise argparse.ArgumentTypeError(f"-maxdownload={v}: allowed auto or 0-100000 (MB), default auto")


def _choice(name, choices, default):
    def conv(v):
        t = str(v).strip().lower()
        if t not in choices:
            raise argparse.ArgumentTypeError(
                f"-{name}={v}: allowed {' | '.join(choices)}, default {default}")
        return t
    return conv


def build_arg_parser():
    p = _Parser(prog="GaiaGlowSubtraction.py", prefix_chars="-",
                allow_abbrev=False, add_help=False,
                description="Subtract bright-star glow using Gaia photometry")
    d = GlowParams()
    p.add_argument("-amount", type=_ranged("amount", 0.0, 1.0, d.amount), default=d.amount)
    p.add_argument("-psf", type=str, default=d.psf)
    p.add_argument("-savepsf", type=str, default="")
    p.add_argument("-auto", type=_bool_arg, nargs="?", const=True, default=True)
    p.add_argument("-faintG", type=_ranged("faintG", 0.0, 16.0, d.faintG), default=d.faintG)
    p.add_argument("-tolerance", type=_ranged("tolerance", 0.0, 1.0, d.tolerance), default=d.tolerance)
    p.add_argument("-protect", type=_ranged("protect", 1e-4, 1.0, d.protect), default=d.protect)
    p.add_argument("-brightprotect", type=_ranged("brightprotect", 0.0, 1.0, d.brightprotect),
                   default=d.brightprotect)
    p.add_argument("-bgorder", type=_ranged("bgorder", 1, 3, d.bgorder, int), default=d.bgorder)
    p.add_argument("-maxradius", type=_ranged("maxradius", 5.0, 90.0, d.maxradius), default=d.maxradius)
    p.add_argument("-passes", type=_choice("passes", ("auto", "1", "2"), "auto"), default="auto")
    p.add_argument("-maxdownload", type=_download_arg, default=d.maxdownload)
    p.add_argument("-glowimage", type=_bool_arg, nargs="?", const=True, default=False)
    p.add_argument("-catsource", type=_choice("catsource", ("auto", "local", "remote", "teff"), "auto"),
                   default="auto")
    p.add_argument("-force", type=_bool_arg, nargs="?", const=True, default=False)
    p.add_argument("-overwrite", type=_bool_arg, nargs="?", const=True, default=False)
    p.add_argument("-offline-ok", dest="offline_ok", type=_bool_arg, nargs="?", const=True,
                   default=False)
    return p


def parse_cli(argv):
    """Parse a pyscript argument vector into GlowParams. Unknown arguments
    are an error (spec 15.2 P1)."""
    ns = build_arg_parser().parse_args(argv)
    gp = GlowParams()
    for k in asdict(gp):
        if hasattr(ns, k):
            setattr(gp, k, getattr(ns, k))
    return gp


# ===========================================================================
# 2. Generic numerical helpers
# ===========================================================================

class HardRefusal(Exception):
    """A check that cannot be overridden (spec 15)."""


class SoftRefusal(Exception):
    """A check refused by the user, or in the CLI without -force."""


class Cancelled(Exception):
    """The user cancelled the run."""


def mad_sigma(x):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    return 1.4826 * float(np.median(np.abs(x - np.median(x))))


def smooth_min(a, b, d):
    """Smooth minimum that never exceeds min(a, b), clipped at 0 (C1, no
    kinks). d is the absolute width of the transition (it lowers the result
    by at most d/2 where a == b)."""
    d = np.float32(d)
    # SPEC (round 18): the same operations in the same order, on two
    # temporaries instead of six full-frame ones
    t = np.subtract(a, b)
    np.square(t, out=t)
    t += d * d
    np.sqrt(t, out=t)
    s_ = np.add(a, b)
    s_ -= t
    del t
    s_ *= 0.5
    np.maximum(s_, 0, out=s_)
    return s_.astype(np.float32, copy=False)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def robust_linear_fit(X, y, sigma=None, huber_k=HUBER_K, clip=CLIP_SIGMA,
                      n_iter=12):
    """Huber IRLS followed by sigma clipping. X is (n, m). Returns
    (coef, cov, keep_mask, residuals)."""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n, m = X.shape
    w0 = np.ones(n) if sigma is None else 1.0 / np.maximum(np.asarray(sigma), 1e-12) ** 2
    keep = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    coef = np.zeros(m)
    for clip_round in range(4):
        if keep.sum() < m + 1:
            break
        w = w0.copy()
        for _ in range(n_iter):
            Xk, yk, wk = X[keep], y[keep], w[keep]
            sw = np.sqrt(wk)
            coef, *_ = np.linalg.lstsq(Xk * sw[:, None], yk * sw, rcond=None)
            r = (yk - Xk @ coef) * np.sqrt(w0[keep])
            sc = mad_sigma(r)
            if not np.isfinite(sc) or sc <= 0:
                break
            u = np.abs(r) / (huber_k * sc)
            hw = np.where(u <= 1, 1.0, 1.0 / np.maximum(u, 1e-12))
            w_new = w0.copy()
            w_new[keep] = w0[keep] * hw
            if np.allclose(w_new, w):
                break
            w = w_new
        res = (y - X @ coef)
        sc = mad_sigma(res[keep] * np.sqrt(w0[keep]))
        if not np.isfinite(sc) or sc <= 0:
            break
        new_keep = keep & (np.abs(res * np.sqrt(w0)) <= clip * sc)
        if new_keep.sum() == keep.sum():
            break
        keep = new_keep
    cov = np.full((m, m), np.nan)
    if keep.sum() > m:
        Xk = X[keep] * np.sqrt(w0[keep])[:, None]
        r = (y[keep] - X[keep] @ coef) * np.sqrt(w0[keep])
        s2 = mad_sigma(r) ** 2
        try:
            cov = np.linalg.inv(Xk.T @ Xk) * s2
        except np.linalg.LinAlgError:
            pass
    return coef, cov, keep, y - X @ coef


def huber_scale(y, model, sigma, n_iter=20, huber_k=HUBER_K):
    """Huber fit of a single scale s minimising sum(((y - s*model)/sigma)^2)."""
    y = np.asarray(y, float)
    mdl = np.asarray(model, float)
    sg = np.asarray(sigma, float)
    ok = np.isfinite(y) & np.isfinite(mdl) & np.isfinite(sg) & (sg > 0)
    y, mdl, sg = y[ok], mdl[ok], sg[ok]
    if y.size == 0 or np.all(mdl == 0):
        return float("nan")
    w = np.ones_like(y)
    s_ = 1.0
    for _ in range(n_iter):
        ww = w / sg ** 2
        den = np.sum(ww * mdl * mdl)
        if den <= 0:
            return float("nan")
        s_new = float(np.sum(ww * mdl * y) / den)
        u = np.abs((y - s_new * mdl) / sg) / huber_k
        w = np.where(u <= 1, 1.0, 1.0 / np.maximum(u, 1e-12))
        if abs(s_new - s_) < 1e-6 * max(1.0, abs(s_)):
            s_ = s_new
            break
        s_ = s_new
    return s_


def weighted_median(values, weights):
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if v.size == 0:
        return float("nan")
    o = np.argsort(v)
    v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, 0.5 * c[-1])])


# SPEC (round 18): grouped order statistics. The ring, sector and annulus
# medians were taken with one np.median call per group (2.2 million calls on
# M31). One sort per array now serves all groups; the results are the values
# np.median / np.percentile give on each group, bit for bit (same dtype, the
# mean of the two middle values for an even count, NaN when the group holds a
# NaN), so the outputs do not change.

def group_order(vals, gid, ngroups):
    """Permutation sorting vals by (group, value), NaN last within a group.
    gid holds small non-negative group numbers (< ngroups)."""
    o = np.argsort(vals)
    g = gid[o]
    o2 = np.argsort(g.astype(np.uint16) if ngroups <= 65536 else g, kind="stable")
    return o[o2]


def grouped_median(vs, starts, counts):
    """np.median of each contiguous group vs[starts[k]:starts[k] + counts[k]]
    of values sorted within the groups (group_order). Empty groups give NaN."""
    counts = np.asarray(counts, np.int64)
    out = np.full(counts.size, np.nan, dtype=vs.dtype)
    ok = counts > 0
    if not ok.any():
        return out
    s, c = np.asarray(starts, np.int64)[ok], counts[ok]
    hi = vs[s + c // 2]
    lo = vs[s + (c - 1) // 2]
    m = np.where(c % 2 == 1, hi, np.mean(np.stack([lo, hi]), axis=0))
    out[ok] = np.where(np.isnan(vs[s + c - 1]), vs.dtype.type(np.nan), m)
    return out


def grouped_median_of(vals, gid, ngroups):
    """np.median of vals per group number gid (0..ngroups-1): (medians, counts)."""
    cnt = np.bincount(gid, minlength=ngroups)
    starts = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    return grouped_median(vals[group_order(vals, gid, ngroups)], starts, cnt), cnt


def rowwise_stats(M, valid, nmin):
    """For each row k of M, a_k = M[k, valid[k]] (in column order). Returns a
    list of (rows_q, A_q), one per count q >= nmin, with A_q the stacked a_k
    of the rows holding q values, so that numpy's own median / percentile
    along axis 1 reproduce the 1-D calls on each a_k."""
    nv = valid.sum(axis=1)
    pack = np.take_along_axis(M, np.argsort(~valid, axis=1, kind="stable"), axis=1)
    out = []
    for q in np.unique(nv[nv >= nmin]):
        rows = np.nonzero(nv == q)[0]
        out.append((rows, pack[rows, :q]))
    return out


def sorted_row_percentile(S, n, q):
    """SPEC (round 19): np.percentile(S[k, :n[k]], q) (linear interpolation) for
    each row of S, whose rows are sorted with their n[k] valid values first. NaN
    for rows without values."""
    n = np.asarray(n, np.int64)
    h = q / 100.0 * np.maximum(n - 1, 0)
    k0 = np.floor(h).astype(np.int64)
    k1 = np.minimum(k0 + 1, np.maximum(n - 1, 0))
    r = np.arange(S.shape[0])
    lo = S[r, np.clip(k0, 0, S.shape[1] - 1)]
    hi = S[r, np.clip(k1, 0, S.shape[1] - 1)]
    with np.errstate(invalid="ignore"):
        out = lo + (h - k0) * (hi - lo)
    return np.where(n > 0, out, np.nan)


def block_view(arr, b):
    """Pad a 2-D array with NaN to multiples of b and return the
    (nby, nbx, b*b) block view."""
    h, w = arr.shape
    nby, nbx = -(-h // b), -(-w // b)
    if nby * b != h or nbx * b != w:
        pad = np.full((nby * b, nbx * b), np.nan, dtype=np.float32)
        pad[:h, :w] = arr
        arr = pad
    return arr.reshape(nby, b, nbx, b).swapaxes(1, 2).reshape(nby, nbx, b * b)


def rows_nanmedian(a):
    """SPEC (round 18): np.nanmedian(a, axis=1) for a 2-D array whose rows each
    hold a non-NaN value, by one row sort, with numpy's own arithmetic: rows
    shorter than 600 take (low + high) / 2 of the two middle values (numpy's
    masked-array path, low = high for an odd count), longer rows the middle
    value or the mean of the two (np.median)."""
    s = np.sort(a, axis=1)
    n = a.shape[1] - np.count_nonzero(np.isnan(a), axis=1)
    hi = np.take_along_axis(s, (n // 2)[:, None], axis=1)[:, 0]
    lo = np.take_along_axis(s, ((n - 1) // 2)[:, None], axis=1)[:, 0]
    if a.shape[1] < 600:
        return (lo + hi) / a.dtype.type(2)
    return np.where(n % 2 == 1, hi, (lo + hi) / a.dtype.type(2))


def masked_block_median(img, valid, b, min_valid=BLOCK_MIN_VALID, rows_per_chunk=None):
    """Block median of img over pixels where valid is True. Blocks with less
    than min_valid of their pixels valid are NaN. Returns (med, frac)."""
    h, w = img.shape
    nby, nbx = -(-h // b), -(-w // b)
    out = np.full((nby, nbx), np.nan, dtype=np.float32)
    frac = np.zeros((nby, nbx), dtype=np.float32)
    step = max(1, int(rows_per_chunk or max(1, 4_000_000 // max(1, w * b))))
    for by0 in range(0, nby, step):
        by1 = min(nby, by0 + step)
        y0, y1 = by0 * b, min(h, by1 * b)
        sub = np.where(valid[y0:y1], img[y0:y1], np.nan).astype(np.float32)
        bv = block_view(sub, b)[: by1 - by0]
        cnt = np.sum(np.isfinite(bv), axis=2)
        frac[by0:by1] = cnt / float(b * b)
        good = cnt >= min_valid * b * b
        if np.any(good):
            with np.errstate(all="ignore"):
                med = rows_nanmedian(bv[good])
            o = out[by0:by1]
            o[good] = med
    return out, frac


def coarse_axis_weights(n_native, b, n_coarse, start=0, stop=None):
    """Linear interpolation from cell centres (point samples) to native pixel
    indices start..stop-1. Returns (i0, i1, w1)."""
    if stop is None:
        stop = n_native
    x = np.arange(start, stop, dtype=np.float64)
    u = (x + 0.5) / b - 0.5
    u = np.clip(u, 0.0, n_coarse - 1)
    i0 = np.floor(u).astype(np.int64)
    i0 = np.minimum(i0, max(0, n_coarse - 2))
    i1 = np.minimum(i0 + 1, n_coarse - 1)
    w1 = (u - i0).astype(np.float32)
    return i0, i1, w1


def upsample_coarse(grid, b, shape, y0=0, y1=None, x0=0, x1=None, grid_origin=(0, 0)):
    """Bilinear upsampling of a point-sampled coarse grid (cell centres) to
    the native pixels [y0:y1, x0:x1]. grid_origin is the coarse index of
    grid[0, 0] (used for patches of the global grid)."""
    h, w = shape
    y1 = h if y1 is None else y1
    x1 = w if x1 is None else x1
    gy0, gx0 = grid_origin
    ncy_tot = -(-h // b)
    ncx_tot = -(-w // b)
    yi0, yi1, wy = coarse_axis_weights(h, b, ncy_tot, y0, y1)
    xi0, xi1, wx = coarse_axis_weights(w, b, ncx_tot, x0, x1)
    gh, gw = grid.shape

    def take(iy, ix):
        ly = iy - gy0
        lx = ix - gx0
        oky = (ly >= 0) & (ly < gh)
        okx = (lx >= 0) & (lx < gw)
        if oky.all() and okx.all():
            # SPEC (round 18): all samples inside the grid (the usual case): the
            # 0/1 masks would multiply every value by 1
            return grid[ly][:, lx].astype(np.float32, copy=False)
        out = np.zeros((iy.size, ix.size), dtype=np.float32)
        if np.any(oky) and np.any(okx):
            sub = grid[np.clip(ly, 0, gh - 1)][:, np.clip(lx, 0, gw - 1)]
            sub = sub * oky[:, None] * okx[None, :]
            out[:] = sub
        return out

    a = take(yi0, xi0)
    bb = take(yi0, xi1)
    c = take(yi1, xi0)
    d = take(yi1, xi1)
    top = a + (bb - a) * wx[None, :]
    bot = c + (d - c) * wx[None, :]
    return top + (bot - top) * wy[:, None]


def normalised_convolution_fill(grid, sigma=2.0):
    """Fill NaN cells by normalised Gaussian convolution of the valid cells."""
    ok = np.isfinite(grid)
    if ok.all():
        return grid.copy()
    g = np.where(ok, grid, 0.0)
    num = ndimage.gaussian_filter(g.astype(np.float64), sigma, mode="nearest")
    den = ndimage.gaussian_filter(ok.astype(np.float64), sigma, mode="nearest")
    with np.errstate(all="ignore"):
        filled = num / den
    out = np.where(ok, grid, filled)
    out = np.where(np.isfinite(out), out, 0.0)
    return out.astype(np.float32)


def available_memory_bytes():
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        return None


class Report:
    """Collects log lines, warnings and the key numbers of the run."""

    def __init__(self, log_fn=None):
        self.log_fn = log_fn or (lambda msg, kind="info": print(msg))
        self.warnings = []
        self.informs = []
        self.numbers = {}
        self.t0 = time.time()

    def info(self, msg):
        self.informs.append(msg)
        self.log_fn(msg, "info")

    def warn(self, msg):
        self.warnings.append(msg)
        self.log_fn("Warning: " + msg, "warn")

    def number(self, key, value):
        self.numbers[key] = value

    def elapsed(self):
        return time.time() - self.t0


# ===========================================================================
# 3. Catalogue access (spec 4)
# ===========================================================================

class CatalogueError(Exception):
    pass


class RemoteError(Exception):
    pass


def parse_healpix_header(buf):
    """Parse the packed 128-byte Siril HEALPix catalogue header."""
    if buf is None or len(buf) < HEADER_SIZE:
        raise CatalogueError("header shorter than 128 bytes")
    t = struct.unpack(HEADER_STRUCT, bytes(buf[:HEADER_SIZE]))
    return {
        "title": t[0].split(b"\0")[0].decode("ascii", "replace"),
        "gaia_version": t[1], "healpix_level": t[2], "cat_type": t[3],
        "chunked": t[4], "chunk_level": t[5], "chunk_healpix": t[6],
        "chunk_first": t[7], "chunk_last": t[8],
    }


def chunk_of_pixel(pix):
    return np.asarray(pix, dtype=np.int64) >> (2 * (HP_LEVEL - CHUNK_LEVEL))


def pixel_runs(pixels):
    """Group sorted pixel ids into runs of consecutive ids: [(start, end)]."""
    p = np.unique(np.asarray(pixels, dtype=np.int64))
    if p.size == 0:
        return []
    breaks = np.nonzero(np.diff(p) != 1)[0]
    starts = np.concatenate([[p[0]], p[breaks + 1]])
    ends = np.concatenate([p[breaks], [p[-1]]])
    return list(zip(starts.tolist(), ends.tolist()))


def validate_chunk_header(h, c, expect_type=CAT_XPSAMP):
    if h["cat_type"] != expect_type:
        return f"cat_type {h['cat_type']} (expected {expect_type})"
    if h["healpix_level"] != HP_LEVEL:
        return f"HEALPix level {h['healpix_level']}"
    if not h["chunked"] or h["chunk_level"] != CHUNK_LEVEL:
        return "not a level-1 chunk"
    if h["chunk_healpix"] != c or h["chunk_first"] != c * N_INDEX_CHUNK:
        return f"chunk number mismatch ({h['chunk_healpix']} != {c})"
    return None


def validate_index(idx):
    if idx.size and np.any(np.diff(idx.astype(np.int64)) < 0):
        return "index is not monotonic"
    return None


def julian_year(dt):
    """Julian epoch of a datetime (naive = UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    jd = (dt - datetime(2000, 1, 1, 12, 0, 0)).total_seconds() / 86400.0 + 2451545.0
    return 2000.0 + (jd - 2451545.0) / 365.25


def propagate(ra, dec, pmra, pmdec, dyr):
    """Siril's proper-motion propagation: pmra includes cos(dec)."""
    if not dyr:
        return ra, dec
    cosd = np.cos(np.radians(dec))
    cosd = np.where(np.abs(cosd) < 1e-6, 1e-6, cosd)
    return (ra + pmra / cosd * dyr / 3.6e6, dec + pmdec * dyr / 3.6e6)


def angular_sep_deg(ra1, dec1, ra2, dec2):
    r1, d1, r2, d2 = map(np.radians, (ra1, dec1, ra2, dec2))
    a = (np.sin((d2 - d1) / 2) ** 2
         + np.cos(d1) * np.cos(d2) * np.sin((r2 - r1) / 2) ** 2)
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def radec_to_unit(ra, dec):
    r, d = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(d) * np.cos(r), np.cos(d) * np.sin(r), np.sin(d)], axis=-1)


def cone_pixels(ra, dec, radius_deg):
    """Level-8 nested HEALPix pixels overlapping a cone, padded by about one
    pixel radius (spec 4.1)."""
    from astropy_healpix import HEALPix
    import astropy.units as u
    hp = HEALPix(nside=HP_NSIDE, order="nested")
    pad = hp.pixel_resolution.to(u.deg).value * 0.75
    pix = hp.cone_search_lonlat(ra * u.deg, dec * u.deg,
                                radius=min(180.0, radius_deg + pad) * u.deg)
    return np.unique(np.asarray(pix, dtype=np.int64))


XP_DENSITY_GMAX = XP_G_MAX  # Siril's xpsamp catalogue holds G <= 15


def xp_density_model(b_deg):
    """Rough number of Gaia XP sources per deg^2 at galactic latitude b, used
    only when no index or local catalogue is available for the estimate."""
    return 300.0 + 12000.0 * math.exp(-abs(b_deg) / 8.0)


def estimate_xp_download(header, shape, cfg, userdatadir):
    """SPEC (round 5): no-network estimate of the remote XP download for the
    image footprint, before a run. Per HEALPix pixel the record count comes
    from (1) a cached chunk index in Siril's spcc-cache, (2) the local
    astrometric extract (stars with G <= 15), or (3) a galactic-latitude
    density model. Bytes already in Siril's SQLite cache are subtracted
    (read-only). Returns a dict: need_mb, cached_mb, local (bool: local XP
    installed, nothing to download), method; or None without a WCS."""
    try:
        geom = ImageGeometry(header, shape)
        ra_c, dec_c = float(geom.center[0][0]), float(geom.center[1][0])
        pix = cone_pixels(ra_c, dec_c, geom.half_diag_deg)
    except Exception:
        return None
    chunks = np.unique(chunk_of_pixel(pix))
    photo = cfg("core", "catalogue_gaia_photo") if cfg else None
    if photo and os.path.isdir(photo) and all(
            os.path.isfile(os.path.join(photo, XP_FILE_TEMPLATE.format(c=int(c)))) for c in chunks):
        return {"need_mb": 0.0, "cached_mb": 0.0, "local": True, "method": "local XP"}
    cache_dir = os.path.join(userdatadir, "spcc-cache") if userdatadir else None
    counts = np.full(pix.size, -1.0)
    method = set()
    for c in chunks:
        sel = chunk_of_pixel(pix) == c
        ip = os.path.join(cache_dir, XP_FILE_TEMPLATE.format(c=int(c)) + ".index") if cache_dir else None
        if ip and os.path.isfile(ip) and os.path.getsize(ip) == 4 * N_INDEX_CHUNK:
            idx = np.fromfile(ip, dtype="<u4").astype(np.int64)
            lp = pix[sel] - int(c) * N_INDEX_CHUNK
            prev = np.where(lp > 0, idx[np.maximum(lp - 1, 0)], 0)
            counts[sel] = idx[lp] - prev
            method.add("cached index")
    todo = counts < 0
    if np.any(todo):
        astro = LocalAstroCatalogue(cfg("core", "catalogue_gaia_astro") if cfg else None)
        if astro.ok:
            try:
                _, hp = astro.read(pix[todo], gmax=XP_DENSITY_GMAX)
                counts[todo] = np.array([np.sum(hp == q) for q in pix[todo]], float)
                method.add("local astrometric counts")
                todo = counts < 0
            except Exception:
                pass
    if np.any(todo):
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        b = float(SkyCoord(ra_c * u.deg, dec_c * u.deg).galactic.b.deg)
        area = 41252.96 / (12 * HP_NSIDE ** 2)
        counts[todo] = xp_density_model(b) * area
        method.add("density model")
    total = float(np.sum(counts)) * REC_XP
    cached = 0.0
    if cache_dir:
        from urllib.parse import quote
        for c in chunks:
            path = os.path.join(cache_dir, XP_FILE_TEMPLATE.format(c=int(c)) + ".cache")
            if not os.path.isfile(path):
                continue
            con = None
            try:
                con = sqlite3.connect(f"file:{quote(path)}?mode=ro", uri=True, timeout=5)
                plist = [int(q) for q in pix[chunk_of_pixel(pix) == c]]
                for i in range(0, len(plist), 500):
                    part = plist[i:i + 500]
                    q = ("SELECT SUM(length(data)) FROM flux_cache WHERE hp_id IN (%s)"
                         % ",".join("?" * len(part)))
                    v = con.execute(q, part).fetchone()[0]
                    cached += float(v or 0)
            except sqlite3.Error:
                pass
            finally:
                if con is not None:
                    con.close()
    cached = min(cached, total)
    return {"need_mb": (total - cached) / 1e6, "cached_mb": cached / 1e6, "local": False,
            "method": ", ".join(sorted(method))}


def download_limit_mb(params, estimate):
    """SPEC (round 5): -maxdownload=auto (default) allows twice the
    pre-run estimate, at least 50 MB; a number is a fixed limit in MB."""
    if params.maxdownload in (None, "auto"):
        need = estimate["need_mb"] if estimate else 0.0
        return max(AUTO_DOWNLOAD_FLOOR_MB, 2.0 * need)
    return float(params.maxdownload)


class StarTable:
    """Column store of catalogue stars. All columns are numpy arrays."""
    COLS = ("ra", "dec", "ra0", "dec0", "pmra", "pmdec", "g", "teff", "hp",
            "key", "src", "xp_row", "bv", "name",
            "hip", "vmag", "ebv", "vi", "evi", "sig_var", "sig_mult")
    # SPEC (round 15): hip..sig_mult hold the Hipparcos photometry of table stars (route B):
    # HIP number (-1 if none), V, B-V errors, V-I and its error, and the variability and
    # multiplicity terms of the flux prior (mag)
    HIP_COLS = ("vmag", "ebv", "vi", "evi", "sig_var", "sig_mult")

    def __init__(self, **cols):
        n = len(cols.get("g", []))
        self.ra = np.asarray(cols.get("ra", np.zeros(n)), float)
        self.dec = np.asarray(cols.get("dec", np.zeros(n)), float)
        self.ra0 = np.asarray(cols.get("ra0", self.ra), float)
        self.dec0 = np.asarray(cols.get("dec0", self.dec), float)
        self.pmra = np.asarray(cols.get("pmra", np.zeros(n)), float)
        self.pmdec = np.asarray(cols.get("pmdec", np.zeros(n)), float)
        self.g = np.asarray(cols.get("g", np.zeros(n)), float)
        self.teff = np.asarray(cols.get("teff", np.full(n, np.nan)), float)
        self.hp = np.asarray(cols.get("hp", np.full(n, -1)), np.int64)
        self.key = np.asarray(cols.get("key", np.full(n, -1)), np.int64)
        self.src = np.asarray(cols.get("src", np.full(n, "A")), "<U1")
        self.xp_row = np.asarray(cols.get("xp_row", np.full(n, -1)), np.int64)
        self.bv = np.asarray(cols.get("bv", np.full(n, np.nan)), float)
        self.name = np.asarray(cols.get("name", np.full(n, "")), object)
        self.hip = np.asarray(cols.get("hip", np.full(n, -1)), np.int64)
        for c in self.HIP_COLS:
            setattr(self, c, np.asarray(cols.get(c, np.full(n, np.nan)), float))
        self.xp = cols.get("xp", np.zeros((0, XP_NWL), np.float32))

    def __len__(self):
        return self.g.size

    def subset(self, m):
        t = StarTable(**{c: getattr(self, c)[m] for c in self.COLS})
        t.xp = self.xp
        return t

    @staticmethod
    def concat(a, b):
        cols = {c: np.concatenate([getattr(a, c), getattr(b, c)]) for c in StarTable.COLS}
        xb = b.xp_row.copy()
        xb[xb >= 0] += a.xp.shape[0]
        cols["xp_row"] = np.concatenate([a.xp_row, xb])
        cols["xp"] = np.concatenate([a.xp, b.xp]) if b.xp.shape[0] else a.xp
        return StarTable(**cols)


def make_key(ra_i, dec_i):
    return (np.asarray(ra_i, np.int64) << 32) | (np.asarray(dec_i, np.int64) & 0xFFFFFFFF)


def decode_xp_flux(recs):
    """XP sampled flux in W m^-2 nm^-1 (spec 4.2 B)."""
    f = recs["flux"].astype(np.float32)
    return f / np.power(10.0, recs["fexpo"].astype(np.float32))[:, None]


class LocalAstroCatalogue:
    """Source A: Siril's monolithic astrometric extract (16-byte records)."""

    def __init__(self, path):
        self.path = path
        self.ok = False
        self.reason = ""
        try:
            if not path or not os.path.isfile(path):
                self.reason = "not installed"
                return
            with open(path, "rb") as fh:
                hdr = parse_healpix_header(fh.read(HEADER_SIZE))
            if hdr["cat_type"] != CAT_ASTRO or hdr["healpix_level"] != HP_LEVEL or hdr["chunked"]:
                self.reason = f"unexpected header {hdr}"
                return
            self.idx = np.memmap(path, dtype="<u4", mode="r", offset=HEADER_SIZE,
                                 shape=(N_INDEX_ASTRO,))
            err = validate_index(self.idx)
            if err:
                self.reason = err
                return
            n = int(self.idx[-1])
            expect = HEADER_SIZE + 4 * N_INDEX_ASTRO + n * REC_ASTRO
            size = os.path.getsize(path)
            if size != expect:
                self.reason = f"size {size} != expected {expect}"
                return
            self.recs = np.memmap(path, dtype=ASTRO_DTYPE, mode="r",
                                  offset=HEADER_SIZE + 4 * N_INDEX_ASTRO, shape=(n,))
            self.ok = True
        except Exception as e:  # pragma: no cover - defensive
            self.reason = str(e)

    def read(self, pixels, gmax=G_KEEP_MAX):
        out_r, out_p = [], []
        for a, b in pixel_runs(pixels):
            i0 = 0 if a == 0 else int(self.idx[a - 1])
            i1 = int(self.idx[b])
            if i1 <= i0:
                continue
            r = np.array(self.recs[i0:i1])
            counts = np.diff(np.concatenate([[i0], self.idx[a:b + 1].astype(np.int64)]))
            pid = np.repeat(np.arange(a, b + 1, dtype=np.int64), counts)
            keep = r["g"] / 1000.0 <= gmax
            out_r.append(r[keep])
            out_p.append(pid[keep])
        if not out_r:
            return np.zeros(0, ASTRO_DTYPE), np.zeros(0, np.int64)
        return np.concatenate(out_r), np.concatenate(out_p)


class LocalXpChunk:
    """Source B: one local xpsamp chunk, validated as a whole (spec 4.1)."""

    def __init__(self, path, c):
        self.path, self.c = path, c
        self.ok = False
        self.reason = ""
        try:
            if not os.path.isfile(path):
                self.reason = "not installed"
                return
            with open(path, "rb") as fh:
                self.header = parse_healpix_header(fh.read(HEADER_SIZE))
            err = validate_chunk_header(self.header, c)
            if err:
                self.reason = err
                return
            self.idx = np.fromfile(path, dtype="<u4", count=N_INDEX_CHUNK, offset=HEADER_SIZE)
            if self.idx.size != N_INDEX_CHUNK:
                self.reason = "index truncated"
                return
            err = validate_index(self.idx)
            if err:
                self.reason = err
                return
            n = int(self.idx[-1])
            expect = HEADER_SIZE + 4 * N_INDEX_CHUNK + n * REC_XP
            size = os.path.getsize(path)
            if size != expect:
                self.reason = f"size {size} B != {expect} B implied by its index (truncated?)"
                return
            self.recs = np.memmap(path, dtype=XP_DTYPE, mode="r",
                                  offset=HEADER_SIZE + 4 * N_INDEX_CHUNK, shape=(n,))
            self.ok = True
        except Exception as e:
            self.reason = str(e)

    def read(self, pixels):
        """Return {global_hp: records} for the requested pixels."""
        base = self.c * N_INDEX_CHUNK
        out = {}
        for a, b in pixel_runs(pixels):
            la, lb = a - base, b - base
            for lp in range(la, lb + 1):
                i0 = 0 if lp == 0 else int(self.idx[lp - 1])
                i1 = int(self.idx[lp])
                out[base + lp] = np.array(self.recs[i0:i1])
        return out


class RemoteXpSource:
    """Source C: remote xpsamp chunks read with HTTP Range requests, using
    Siril's spcc-cache read-only first and writing back only into cache
    databases that Siril already created (spec 4.3)."""

    def __init__(self, cache_dir, ctx, mirrors=REMOTE_MIRRORS):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ctx = ctx
        self.mirrors = list(mirrors)
        self.meta = {}
        self.session = None
        self.bytes_fetched = 0
        self.unreachable = False
        self.write_warned = False

    # -- HTTP ------------------------------------------------------------
    def _session(self):
        if self.session is None:
            import requests
            self.session = requests.Session()
            self.session.headers["User-Agent"] = f"GaiaGlowSubtraction/{VERSION}"
        return self.session

    def _get_range(self, fname, start, length):
        import requests
        last = None
        for mirror in self.mirrors:
            url = f"{mirror}/{fname}"
            for attempt in range(HTTP_RETRIES + 1):
                self.ctx.check_cancel()
                try:
                    with self._session().get(
                            url, headers={"Range": f"bytes={start}-{start + length - 1}"},
                            timeout=HTTP_TIMEOUT, stream=True) as r:
                        if r.status_code == 206:
                            data = r.raw.read(length + 1, decode_content=True)
                            if len(data) != length:
                                raise RemoteError(f"length {len(data)} != {length}")
                            self.bytes_fetched += length
                            return data
                        if r.status_code in (429, 500, 502, 503, 504):
                            last = RemoteError(f"HTTP {r.status_code}")
                        else:
                            # 200 means the server ignored the Range: reject,
                            # as Siril does, without reading the body.
                            raise RemoteError(f"HTTP {r.status_code} (206 required)")
                except RemoteError as e:
                    last = e
                    if "206 required" in str(e):
                        break
                except requests.RequestException as e:
                    last = e
                if attempt < HTTP_RETRIES:
                    time.sleep(min(8.0, 1.0 * 2 ** attempt))
        raise RemoteError(str(last))

    # -- chunk metadata ----------------------------------------------------
    def _cache_file(self, c, suffix):
        if self.cache_dir is None:
            return None
        return self.cache_dir / (XP_FILE_TEMPLATE.format(c=c) + suffix)

    def _write_side_file(self, path, data):
        """Write .header/.index only if absent or the wrong size (atomic)."""
        try:
            if path is None or not path.parent.is_dir():
                return
            if path.exists() and path.stat().st_size == len(data):
                return
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ggs_")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, str(path))
        except Exception as e:
            self._warn_write(e)

    def _warn_write(self, e):
        if not self.write_warned:
            self.ctx.report.warn(f"could not write to Siril's catalogue cache ({e}); "
                                 "continuing without caching")
            self.write_warned = True

    def chunk_meta(self, c):
        if c in self.meta:
            return self.meta[c]
        fname = XP_FILE_TEMPLATE.format(c=c)
        hdr_b = None
        p = self._cache_file(c, ".header")
        if p is not None and p.is_file() and p.stat().st_size == HEADER_SIZE:
            hdr_b = p.read_bytes()
            try:
                if validate_chunk_header(parse_healpix_header(hdr_b), c):
                    hdr_b = None
            except CatalogueError:
                hdr_b = None
        fetched_hdr = False
        if hdr_b is None:
            hdr_b = self._get_range(fname, 0, HEADER_SIZE)
            fetched_hdr = True
        h = parse_healpix_header(hdr_b)
        err = validate_chunk_header(h, c)
        if err:
            raise RemoteError(f"remote chunk {c}: {err}")
        idx_b = None
        p_idx = self._cache_file(c, ".index")
        if p_idx is not None and p_idx.is_file() and p_idx.stat().st_size == 4 * N_INDEX_CHUNK:
            idx_b = p_idx.read_bytes()
        fetched_idx = False
        if idx_b is None:
            idx_b = self._get_range(fname, HEADER_SIZE, 4 * N_INDEX_CHUNK)
            fetched_idx = True
        idx = np.frombuffer(idx_b, dtype="<u4").copy()
        err = validate_index(idx)
        if err:
            raise RemoteError(f"remote chunk {c}: {err}")
        if fetched_hdr:
            self._write_side_file(p, hdr_b)
        if fetched_idx:
            self._write_side_file(p_idx, idx_b)
        self.meta[c] = (h, idx)
        return self.meta[c]

    def pixel_count(self, c, hp):
        _, idx = self.chunk_meta(c)
        lp = int(hp) - c * N_INDEX_CHUNK
        i0 = 0 if lp == 0 else int(idx[lp - 1])
        return int(idx[lp]) - i0

    # -- Siril's SQLite cache ----------------------------------------------
    def read_cache(self, c, pixels):
        """Read-only lookup in Siril's cache. Returns {hp: records}."""
        path = self._cache_file(c, ".cache")
        out = {}
        if path is None or not path.is_file():
            return out
        from urllib.parse import quote
        con = None
        try:
            con = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)
            plist = [int(p) for p in pixels]
            for i in range(0, len(plist), 500):
                part = plist[i:i + 500]
                q = "SELECT hp_id, data FROM flux_cache WHERE hp_id IN (%s)" % ",".join("?" * len(part))
                for hp, data in con.execute(q, part):
                    n = self.pixel_count(c, hp)
                    blob = b"" if data is None else bytes(data)
                    if len(blob) != n * REC_XP:
                        continue  # stale or foreign entry: fetch it again
                    out[int(hp)] = np.frombuffer(blob, dtype=XP_DTYPE).copy() if n else np.zeros(0, XP_DTYPE)
        except sqlite3.Error:
            return {}
        finally:
            if con is not None:
                con.close()
        return out

    def write_cache(self, c, entries):
        """INSERT OR REPLACE into an existing Siril cache only (spec 4.3)."""
        path = self._cache_file(c, ".cache")
        if path is None or not path.is_file() or not entries:
            return
        items = sorted(entries.items())
        try:
            for i in range(0, len(items), CACHE_BATCH):
                batch = items[i:i + CACHE_BATCH]
                now = int(time.time())
                rows = [(int(hp), now, (None if len(r) == 0 else sqlite3.Binary(r.tobytes())))
                        for hp, r in batch]
                con = sqlite3.connect(str(path), timeout=5)
                try:
                    con.executemany("INSERT OR REPLACE INTO flux_cache (hp_id, timestamp, data) "
                                    "VALUES (?, ?, ?)", rows)
                    con.commit()
                finally:
                    con.close()
        except Exception as e:
            self._warn_write(e)

    # -- fetching ----------------------------------------------------------
    def download_size(self, c, pixels, cached):
        return sum(self.pixel_count(c, p) * REC_XP for p in pixels if p not in cached)

    def fetch(self, c, pixels, cached):
        """Fetch the uncached pixels, one request per run of consecutive
        pixels. A pixel enters the cache only after its whole range passed
        the length check."""
        h, idx = self.chunk_meta(c)
        base = c * N_INDEX_CHUNK
        fname = XP_FILE_TEMPLATE.format(c=c)
        todo = [p for p in pixels if p not in cached]
        out = {}
        for a, b in pixel_runs(todo):
            la, lb = a - base, b - base
            i0 = 0 if la == 0 else int(idx[la - 1])
            i1 = int(idx[lb])
            n = i1 - i0
            if n > 0:
                data = self._get_range(fname, HEADER_SIZE + 4 * N_INDEX_CHUNK + i0 * REC_XP, n * REC_XP)
                recs = np.frombuffer(data, dtype=XP_DTYPE).copy()
            else:
                recs = np.zeros(0, XP_DTYPE)
            run = {}
            for lp in range(la, lb + 1):
                p0 = (0 if lp == 0 else int(idx[lp - 1])) - i0
                p1 = int(idx[lp]) - i0
                run[base + lp] = recs[p0:p1]
            out.update(run)
            self.write_cache(c, run)
            self.ctx.progress(f"Catalogue download {self.bytes_fetched / 1e6:.1f} MB", -2.0)
        return out


class BrightTableError(Exception):
    pass


def bright_table_path(userdatadir):
    """SPEC (round 16): the cache sits next to last_output.json (SirilIO._fp_path)."""
    return os.path.join(userdatadir, "gaiaglowsubtraction", BRIGHT_FILE) if userdatadir else None


def _num(v):
    v = (v or "").strip()
    return float(v) if v else None


def fetch_bright_csv(url=BRIGHT_TAP_URL, timeout=BRIGHT_TIMEOUT):
    """Read-only VizieR TAP query (stdlib only). Returns the CSV text."""
    import urllib.parse
    import urllib.request
    data = urllib.parse.urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                                   "QUERY": BRIGHT_QUERY}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": f"GaiaGlowSubtraction/{VERSION}"})
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(BRIGHT_MAX_BYTES + 1)
            if len(raw) > BRIGHT_MAX_BYTES:
                raise BrightTableError(f"answer larger than {BRIGHT_MAX_BYTES // 1024} kB")
            return raw.decode("utf-8")
        except BrightTableError:
            raise
        except Exception as e:
            last = e
    raise BrightTableError(f"VizieR query failed ({last})")


def bright_star_names(systemdatadir):
    """Names from Siril's stars.csv (cosmetic, logs only): [(name, ra, dec, V)] at J2000."""
    out = []
    path = Path(systemdatadir) / "catalogue" / "stars.csv" if systemdatadir else None
    if path is None or not path.is_file():
        return out
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    out.append((r["name"].strip(), float(r["ra"]), float(r["dec"]), float(r["mag"])))
                except (KeyError, ValueError):
                    continue
    except OSError:
        pass
    return out


def build_bright_rows(text, names):
    """VizieR CSV -> table rows (the processing of the round-15 generator): errors rounded
    up to 0.01 mag, the variability amplitude as HPmin - Hpmax, a name from stars.csv
    (nearest within 30" at J2000 and |dV| < 0.6) or 'HIP n'."""
    rd = csv.DictReader(StringIO(text))
    need = {"HIP", "RAICRS", "DEICRS", "pmRA", "pmDE", "Vmag", "VarFlag", "B-V", "e_B-V", "V-I",
            "e_V-I", "Hpmax", "HPmin", "MultFlag", "Ncomp", "rho", "dHp"}
    if rd.fieldnames is None or not need.issubset(rd.fieldnames):
        raise BrightTableError("unexpected VizieR answer (columns " + str(rd.fieldnames)[:200] + ")")
    err = lambda v: None if v is None else max(0.01, math.ceil(round(v * 100, 6)) / 100.0)
    rows = []
    for r in rd:
        try:
            hip = int(r["HIP"])
            ra, dec, v = float(r["RAICRS"]), float(r["DEICRS"]), float(r["Vmag"])
        except (TypeError, ValueError):
            continue
        pmra, pmdec = _num(r["pmRA"]) or 0.0, _num(r["pmDE"]) or 0.0
        hmax, hmin = _num(r["Hpmax"]), _num(r["HPmin"])
        name = f"HIP {hip}"
        ra20, de20 = propagate(ra, dec, pmra, pmdec, 2000.0 - HIP_EPOCH)
        best = None
        for nm, nra, nde, nv in names:
            if abs(nde - de20) > 0.01 or abs(nv - v) >= 0.6:
                continue
            sep = float(angular_sep_deg(ra20, de20, nra, nde)) * 3600.0
            if sep < 30.0 and (best is None or sep < best[0]):
                best = (sep, nm)
        if best:
            name = best[1]
        rows.append((hip, round(ra, 5), round(dec, 5), int(round(pmra)), int(round(pmdec)), round(v, 2),
                     None if _num(r["B-V"]) is None else round(_num(r["B-V"]), 2), err(_num(r["e_B-V"])),
                     None if _num(r["V-I"]) is None else round(_num(r["V-I"]), 2), err(_num(r["e_V-I"])),
                     int(r["VarFlag"]) if (r["VarFlag"] or "").strip() else 0,
                     round(hmin - hmax, 2) if (hmax is not None and hmin is not None) else None,
                     (r["MultFlag"] or "").strip(), int(r["Ncomp"]) if (r["Ncomp"] or "").strip() else 1,
                     None if _num(r["rho"]) is None else round(_num(r["rho"]), 1),
                     None if _num(r["dHp"]) is None else round(_num(r["dHp"]), 2), name))
    return rows


def bright_cache_text(rows, date):
    """The cache file: '#' header lines (source, query, selection, date, format), one CSV
    header line, one line per star; empty field = no value."""
    hdr = [f"# GaiaGlowSubtraction bright-star table, format {BRIGHT_FORMAT}",
           "# source: Hipparcos main catalogue (ESA 1997, ESA SP-1200), VizieR I/239/hip_main",
           f"# service: {BRIGHT_TAP_URL}",
           f"# query: {BRIGHT_QUERY}",
           f"# selection: Vmag < {BRIGHT_VMAX}",
           f"# date: {date}",
           f"# rows: {len(rows)}",
           "# units: ra, dec ICRS deg at J1991.25; pmra (includes cos dec), pmdec mas/yr; mag; "
           "errors rounded up to 0.01; var = VarFlag; amp = HPmin - Hpmax; rho arcsec",
           ",".join(BRIGHT_COLUMNS)]
    buf = StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for t in rows:
        w.writerow(["" if x is None else (f"{x:.5f}" if k in ("ra", "dec") else x)
                    for k, x in zip(BRIGHT_COLUMNS, t)])
    return "\n".join(hdr) + "\n" + buf.getvalue()


def parse_bright_cache(text):
    """Validate and parse a cache file: format version, selection, columns, row count.
    Returns (rows, meta) or raises BrightTableError."""
    lines = text.splitlines()
    meta = {}
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        k, _, v = lines[i][1:].partition(":")
        meta[k.strip()] = v.strip()
        i += 1
    first = lines[0] if lines else ""
    if not first.startswith("# GaiaGlowSubtraction bright-star table, format "):
        raise BrightTableError("not a bright-star table")
    if first.rsplit(" ", 1)[-1] != str(BRIGHT_FORMAT):
        raise BrightTableError(f"format {first.rsplit(' ', 1)[-1]} (expected {BRIGHT_FORMAT})")
    if meta.get("selection") != f"Vmag < {BRIGHT_VMAX}":
        raise BrightTableError(f"selection '{meta.get('selection')}' (expected Vmag < {BRIGHT_VMAX})")
    if i >= len(lines) or lines[i].strip() != ",".join(BRIGHT_COLUMNS):
        raise BrightTableError("unexpected columns")
    rows = []
    ints = {"hip", "pmra", "pmdec", "var", "ncomp"}
    for rec in csv.reader(lines[i + 1:]):
        if not rec:
            continue
        if len(rec) != len(BRIGHT_COLUMNS):
            raise BrightTableError(f"row with {len(rec)} fields")
        try:
            t = []
            for k, x in zip(BRIGHT_COLUMNS, rec):
                if k in ("mult", "name"):
                    t.append(x)
                elif x == "":
                    t.append(None)
                else:
                    t.append(int(x) if k in ints else float(x))
        except ValueError:
            raise BrightTableError("unparsable row")
        if t[0] is None or t[1] is None or t[2] is None or t[5] is None or not t[5] < BRIGHT_VMAX:
            raise BrightTableError(f"bad row for HIP {t[0]}")
        rows.append(tuple(t))
    if not BRIGHT_ROWS[0] <= len(rows) <= BRIGHT_ROWS[1] or str(len(rows)) != meta.get("rows"):
        raise BrightTableError(f"{len(rows)} rows (header says {meta.get('rows')}; "
                               f"expected {BRIGHT_ROWS[0]}-{BRIGHT_ROWS[1]})")
    return rows, meta


def read_bright_cache(path):
    """(rows, meta) of a valid cache file, else (None, reason). No network."""
    if not path or not os.path.isfile(path):
        return None, "no cache file"
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_bright_cache(fh.read())
    except (OSError, UnicodeDecodeError, BrightTableError) as e:
        return None, f"invalid cache ({e})"


def load_bright_table(userdatadir, systemdatadir, allow_network, report):
    """SPEC (round 16): source D rows. A valid cache is used without network access;
    otherwise the table is built from VizieR (if allowed) and written atomically.
    Returns the rows, or None (with a warning) when no table can be had."""
    path = bright_table_path(userdatadir)
    rows, meta = read_bright_cache(path)
    if rows is not None:
        report.info(f"Bright-star table: {len(rows)} Hipparcos stars (V < {BRIGHT_VMAX}) from {path} "
                    f"(built {meta.get('date', '?')})")
        return rows
    why = meta
    if not allow_network:
        reason = f"{why}; -catsource=local allows no network"
    else:
        if path and why != "no cache file":
            report.info(f"Bright-star table at {path}: {why}; rebuilding it")
        t0 = time.time()
        try:
            text = fetch_bright_csv()
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            body = bright_cache_text(build_bright_rows(text, bright_star_names(systemdatadir)), date)
            rows, meta = parse_bright_cache(body)
            note = "not cached (no user data directory)"
            if path:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(body)
                    os.chmod(tmp, 0o644)
                    os.replace(tmp, path)
                    note = f"cached at {path}"
                except OSError as e:
                    note = f"not cached ({e})"
            report.info(f"Bright-star table: {len(rows)} Hipparcos stars (V < {BRIGHT_VMAX}) downloaded "
                        f"from VizieR I/239/hip_main ({len(text) / 1024:.0f} kB, {time.time() - t0:.1f} s), "
                        + note)
            return rows
        except BrightTableError as e:
            reason = str(e)
    report.warn(f"Bright-star table unavailable ({reason}). The run continues without it: stars "
                "brighter than about G = 3 that Gaia lacks (e.g. Sirius, Polaris, zeta Ori) are not "
                f"modelled, and stars brighter than G = {HIP_ROUTE_GMAX:.0f} keep the Gaia XP or Teff "
                "flux instead of the Hipparcos route. Run once with network access to build "
                f"{path or 'the cache'}.")
    return None


class BrightStarSupplement:
    """Source D: the Hipparcos bright-star table (V < BRIGHT_VMAX, epoch J1991.25).
    SPEC (round 15): replaces Siril's stars.csv (V only, no colours, J2000) and the
    hand-typed B-V table of round 1. SPEC (round 16): rows from load_bright_table
    (empty when the table could not be had)."""

    def __init__(self, rows=None):
        self.rows = rows or ()

    @staticmethod
    def g_minus_v(bv):
        """Riello et al. 2021, G - V as a function of B - V."""
        return -0.02704 + 0.01424 * bv - 0.2156 * bv ** 2 + 0.01426 * bv ** 3

    @staticmethod
    def sigma_var(var, amp):
        """Variability term of the flux prior: half the Hp 5-95% range of a star
        flagged variable (VarFlag 1-3), else 0."""
        if not var:
            return 0.0
        if amp is None:
            return {1: 0.03, 2: 0.3}.get(var, 0.6)
        return 0.5 * float(amp)

    def stars(self, ra_c, dec_c, radius_deg, epoch):
        """Table stars inside the cone, propagated from J1991.25 to the epoch
        (DATE-OBS, else J2016.0). Returns a list of dicts."""
        out = []
        dyr = (epoch if epoch else GAIA_EPOCH) - HIP_EPOCH
        for (hip, ra, dec, pmra, pmdec, v, bv, ebv, vi, evi, var, amp, mult, ncomp, rho, dhp,
             name) in self.rows:
            ra_p, dec_p = propagate(np.array(ra), np.array(dec), pmra, pmdec, dyr)
            if angular_sep_deg(ra_c, dec_c, ra_p, dec_p) > radius_deg:
                continue
            out.append({"hip": hip, "name": name, "ra": float(ra_p), "dec": float(dec_p), "vmag": v,
                        "bv": nan_if_none(bv), "ebv": nan_if_none(ebv), "vi": nan_if_none(vi),
                        "evi": nan_if_none(evi),
                        "sig_var": self.sigma_var(var, amp),
                        "sig_mult": HIP_MULT_ERR if (mult or ncomp > 1) else 0.0})
        return out


def nan_if_none(v):
    return float("nan") if v is None else float(v)


def teff_from_bv(bv):
    """Ballesteros (2012)."""
    bv = np.asarray(bv, float)
    return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


class CatalogueService:
    """Query plan of spec 4.4: positions and G, spectra, bright supplement."""

    def __init__(self, ctx, astro_path, photo_dir, cache_dir, catsource="auto"):
        self.ctx = ctx
        self.catsource = catsource
        self.astro = LocalAstroCatalogue(astro_path) if catsource != "remote-only" else None
        self.photo_dir = photo_dir
        self.remote = RemoteXpSource(cache_dir, ctx)
        self.local_chunks = {}
        self.supplement = BrightStarSupplement()    # SPEC (round 16): rows set in _compute
        self.sources_used = {"positions": set(), "spectra": set()}
        self.xp_pixels = {}       # hp -> records (all xpsamp data read this run)
        self.local_invalid = {}

    # -- availability ------------------------------------------------------
    def local_chunk(self, c):
        if c not in self.local_chunks:
            ch = None
            if self.photo_dir and os.path.isdir(self.photo_dir):
                ch = LocalXpChunk(os.path.join(self.photo_dir, XP_FILE_TEMPLATE.format(c=c)), c)
                if not ch.ok and ch.reason != "not installed":
                    self.local_invalid[c] = ch.reason
                    self.ctx.report.warn(f"local XP chunk {c} is unusable ({ch.reason}); "
                                         "falling back to the remote catalogue for it")
            self.local_chunks[c] = ch if (ch is not None and ch.ok) else None
        return self.local_chunks[c]

    def summary(self):
        a = "local astrometric extract" if (self.astro and self.astro.ok) else "none"
        b = "installed" if (self.photo_dir and os.path.isdir(self.photo_dir)) else "not installed"
        return a, b

    # -- xpsamp access -----------------------------------------------------
    def read_xp(self, pixels, allow_local=True, allow_remote=True):
        """Return {hp: records} for the pixels from B, cache or C."""
        pixels = np.unique(np.asarray(pixels, np.int64))
        need = [int(p) for p in pixels if int(p) not in self.xp_pixels]
        by_chunk = {}
        for p in need:
            by_chunk.setdefault(int(p) // N_INDEX_CHUNK, []).append(p)
        remote_plan = []
        for c, plist in sorted(by_chunk.items()):
            ch = self.local_chunk(c) if allow_local else None
            if ch is not None:
                self.xp_pixels.update(ch.read(plist))
                self.sources_used["spectra"].add("local XP (B)")
                continue
            if allow_remote and not self.remote.unreachable:
                remote_plan.append((c, plist))
        if remote_plan:
            try:
                total = 0
                cached_all = {}
                for c, plist in remote_plan:
                    cached = self.remote.read_cache(c, plist)
                    cached_all[c] = cached
                    total += self.remote.download_size(c, plist, cached)
                self.ctx.report.info(f"Remote XP catalogue: {total / 1e6:.1f} MB to download "
                                     f"({sum(len(p) for _, p in remote_plan)} HEALPix pixels, "
                                     f"{sum(len(v) for v in cached_all.values())} from Siril's cache)")
                self.ctx.download_budget(total / 1e6)
                for c, plist in remote_plan:
                    self.xp_pixels.update(cached_all[c])
                    got = self.remote.fetch(c, plist, cached_all[c])
                    self.xp_pixels.update(got)
                    if cached_all[c]:
                        self.sources_used["spectra"].add("Siril SPCC cache")
                    if got:
                        self.sources_used["spectra"].add("remote XP (C, Zenodo)")
            except RemoteError as e:
                self.remote.unreachable = True
                self.ctx.report.warn(f"remote Gaia catalogue unreachable ({e})")
        return {int(p): self.xp_pixels[int(p)] for p in pixels if int(p) in self.xp_pixels}

    # -- step 1: positions -------------------------------------------------
    def positions(self, ra_c, dec_c, radius_deg, epoch):
        pix = cone_pixels(ra_c, dec_c, radius_deg)
        dyr = (epoch - GAIA_EPOCH) if epoch else 0.0
        if self.astro is not None and self.astro.ok and self.catsource != "remote":
            recs, hp = self.astro.read(pix)
            table = StarTable(
                ra0=recs["ra"] * COORD_SCALE, dec0=recs["dec"] * COORD_SCALE,
                pmra=recs["pmra"].astype(float), pmdec=recs["pmdec"].astype(float),
                g=recs["g"] / 1000.0,
                teff=np.where(recs["teff"] > 0, recs["teff"].astype(float), np.nan),
                hp=hp, key=make_key(recs["ra"], recs["dec"]), src=np.full(recs.size, "A"))
            self.sources_used["positions"].add("local astrometric (A)")
            self.position_source = "A"
        else:
            allow_local = self.catsource in ("auto", "local", "teff")
            allow_remote = self.catsource in ("auto", "remote", "teff")
            got = self.read_xp(pix, allow_local=allow_local, allow_remote=allow_remote)
            if not got:
                return None
            recs = np.concatenate([got[p] for p in sorted(got)]) if got else np.zeros(0, XP_DTYPE)
            hp = np.concatenate([np.full(got[p].size, p, np.int64) for p in sorted(got)])
            xp = decode_xp_flux(recs)
            table = StarTable(
                ra0=recs["ra"] * COORD_SCALE, dec0=recs["dec"] * COORD_SCALE,
                pmra=recs["pmra"].astype(float), pmdec=recs["pmdec"].astype(float),
                g=recs["g"] / 1000.0, hp=hp, key=make_key(recs["ra"], recs["dec"]),
                src=np.full(recs.size, "X"), xp_row=np.arange(recs.size), xp=xp)
            self.sources_used["positions"].add("XP catalogue (B/C)")
            self.position_source = "X"
            if self.catsource == "teff":
                table.xp_row[:] = -1
        table.ra, table.dec = propagate(table.ra0, table.dec0, table.pmra, table.pmdec, dyr)
        sep = angular_sep_deg(ra_c, dec_c, table.ra, table.dec)
        return table.subset(sep <= radius_deg)

    # -- step 2: spectra ---------------------------------------------------
    def attach_spectra(self, table, need):
        """Attach XP spectra to the stars flagged in `need` (G <= 15)."""
        if self.catsource == "teff":
            return table
        if self.position_source == "X":
            return table
        need = need & (table.g <= XP_G_MAX) & (table.xp_row < 0) & (table.hp >= 0)
        if not np.any(need):
            return table
        allow_local = self.catsource in ("auto", "local")
        allow_remote = self.catsource in ("auto", "remote")
        got = self.read_xp(np.unique(table.hp[need]), allow_local=allow_local,
                           allow_remote=allow_remote)
        if not got:
            return table
        recs = np.concatenate([got[p] for p in sorted(got)])
        xp_hp = np.concatenate([np.full(got[p].size, p, np.int64) for p in sorted(got)])
        xkey = make_key(recs["ra"], recs["dec"])
        order = np.argsort(xkey)
        xs = xkey[order]
        pos = np.searchsorted(xs, table.key)
        pos = np.clip(pos, 0, max(0, xs.size - 1))
        match = (xs.size > 0) & (xs[pos] == table.key) & np.isin(table.hp, xp_hp)
        cand = np.isin(table.hp, xp_hp) & (table.g <= XP_G_MAX)
        frac = match[cand].mean() if np.any(cand) else 1.0
        row_of = np.full(len(table), -1, np.int64)
        if frac >= JOIN_MIN_FRACTION:
            row_of[match] = order[pos[match]]
        else:
            # SPEC: the exact-join check is made once over all pixels read
            # (not per first chunk); the fallback is a nearest-neighbour join.
            self.ctx.report.info(f"Exact A/XP join matched only {100 * frac:.0f}% of G<=15 "
                                 "stars; using a nearest-neighbour join (0.2\", |dG|<0.02)")
            tree = cKDTree(radec_to_unit(recs["ra"] * COORD_SCALE, recs["dec"] * COORD_SCALE))
            idx = np.nonzero(cand)[0]
            d, j = tree.query(radec_to_unit(table.ra0[idx], table.dec0[idx]),
                              distance_upper_bound=np.radians(JOIN_NN_ARCSEC / 3600.0))
            ok = np.isfinite(d) & (j < recs.size)
            ok[ok] &= np.abs(recs["g"][j[ok]] / 1000.0 - table.g[idx[ok]]) < JOIN_NN_DG
            row_of[idx[ok]] = j[ok]
        have = row_of >= 0
        base = table.xp.shape[0]
        uniq, inv = np.unique(row_of[have], return_inverse=True)
        newxp = decode_xp_flux(recs[uniq]) if uniq.size else np.zeros((0, XP_NWL), np.float32)
        table.xp = np.concatenate([table.xp, newxp]) if table.xp.shape[0] else newxp
        table.xp_row[have] = base + inv
        return table

    # -- step 3: bright supplement ----------------------------------------
    def add_supplement(self, table, ra_c, dec_c, radius_deg, epoch):
        """SPEC (round 15): each table star in the cone either joins its Gaia match
        (within 15" and 1.5 mag) or, with none, is added as a D star. A match
        brighter than HIP_ROUTE_GMAX keeps its Gaia position and gets the Hipparcos
        photometry, so that route B predicts its flux; a fainter match stays on the
        XP route. Gaia stars within HIP_COMBINED_ARCSEC of a route-B or D star and
        less than HIP_COMBINED_DMAG fainter are dropped: Hipparcos V is the combined
        light of the system, so their light would be counted twice (all-sky: route B
        minus XP is -0.19 mag for stars with 10-50% companion light within 10")."""
        d = self.supplement.stars(ra_c, dec_c, radius_deg, epoch)
        info = {"cone": len(d), "matched": 0, "route_b": 0, "added": 0, "dropped": 0}
        if not d:
            return table, info
        add = []
        drop = np.zeros(len(table), bool)
        for st in d:
            bv = st["bv"] if np.isfinite(st["bv"]) else 0.65
            g_est = st["vmag"] + BrightStarSupplement.g_minus_v(bv)
            j = -1
            if len(table):
                sep = angular_sep_deg(st["ra"], st["dec"], table.ra, table.dec) * 3600.0
                near = np.nonzero((sep < D_MATCH_ARCSEC) & (np.abs(table.g - g_est) < D_MATCH_DMAG) & ~drop)[0]
                if near.size:
                    j = int(near[np.argmin(table.g[near])])
            if j >= 0:
                info["matched"] += 1
                if table.g[j] >= HIP_ROUTE_GMAX:
                    continue
                table.hip[j] = st["hip"]
                table.name[j] = st["name"]
                table.bv[j] = st["bv"]
                for c in StarTable.HIP_COLS:
                    getattr(table, c)[j] = st[c]
                if not np.isfinite(table.teff[j]):
                    # Teff fallback if route B cannot be calibrated
                    table.teff[j] = teff_from_bv(bv)
                info["route_b"] += 1
                ref = (table.ra[j], table.dec[j], table.g[j])
            else:
                st["g"] = g_est
                add.append(st)
                ref = (st["ra"], st["dec"], g_est)
            if len(table):
                sep = angular_sep_deg(ref[0], ref[1], table.ra, table.dec) * 3600.0
                comp = (sep < HIP_COMBINED_ARCSEC) & (table.g >= ref[2]) & (table.g < ref[2] + HIP_COMBINED_DMAG)
                if j >= 0:
                    comp[j] = False
                drop |= comp
        if np.any(drop):
            info["dropped"] = int(drop.sum())
            table = table.subset(np.nonzero(~drop)[0])
        if not add:
            return table, info
        n = len(add)
        info["added"] = n
        col = lambda k: np.array([a[k] for a in add])
        bv = col("bv")
        t = StarTable(ra=col("ra"), dec=col("dec"), g=col("g"), bv=bv,
                      teff=teff_from_bv(np.where(np.isfinite(bv), bv, 0.65)),
                      src=np.full(n, "D"), name=np.array([a["name"] for a in add], object),
                      hip=col("hip"), **{c: col(c) for c in StarTable.HIP_COLS})
        self.sources_used["positions"].add("bright-star table (D)")
        return StarTable.concat(table, t), info


# ===========================================================================
# 4. Synthetic photometry (spec 4.5)
# ===========================================================================

def tophat_curve(lo, hi, wl=XP_WL, step=2.0):
    """Fraction of each XP sample bin [wl-1, wl+1] that lies inside [lo, hi]."""
    a = np.clip(np.minimum(wl + step / 2, hi) - np.maximum(wl - step / 2, lo), 0, None)
    return (a / step).astype(np.float64)


def planck_lambda(wl_nm, teff):
    wl = np.asarray(wl_nm, float)[None, :] * 1e-9
    t = np.asarray(teff, float)[:, None]
    with np.errstate(over="ignore"):
        return 1.0 / (wl ** 5 * (np.exp(0.0143877735 / (wl * t)) - 1.0))


class SpccDatabase:
    """Minimal reader for Siril's SPCC JSON database (spec 4.5)."""

    def __init__(self, root):
        self.entries = []
        self.root = Path(root) if root else None
        if self.root is None or not self.root.is_dir():
            return
        for sub in ("mono_filters", "mono_sensors", "osc_sensors", "osc_filters"):
            d = self.root / sub
            if not d.is_dir():
                continue
            for f in d.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for e in (data if isinstance(data, list) else [data]):
                    if isinstance(e, dict) and "wavelength" in e and "values" in e:
                        self.entries.append(e)

    def find(self, pref, channel=None):
        if not pref:
            return None
        for e in self.entries:
            if pref in (e.get("name"), e.get("model")):
                if channel is None or str(e.get("channel", "")).upper() == channel:
                    return e
        return None

    @staticmethod
    def curve(e):
        if e is None:
            return None
        try:
            wl = np.asarray(e["wavelength"]["value"], float)
            units = str(e["wavelength"].get("units", "nm")).lower()
            if units.startswith("a"):
                wl = wl / 10.0
            elif units in ("um", "micrometer", "micron", "µm"):
                wl = wl * 1000.0
            v = np.asarray(e["values"]["value"], float)
            o = np.argsort(wl)
            c = np.interp(XP_WL, wl[o], v[o], left=0.0, right=0.0)
            m = c.max()
            return c / m if m > 0 else None
        except Exception:
            return None


def detect_narrowband_filter(filter_kw):
    t = (filter_kw or "").strip().lower().replace(" ", "")
    if not t:
        return None
    for key, wl in NB_LINES.items():
        if key in t:
            return wl
    m = re.search(r"(\d{3}(?:\.\d+)?)\s*nm", filter_kw or "", re.I)
    if m:
        return float(m.group(1))
    return None


def channel_curves(nc, cfg, spcc_root, filter_kw, report):
    """Channel response curves T_c on the XP grid. cfg is a callable
    (group, key) -> value. Returns (curves[nc, 343], description, nb)."""
    nb = False
    desc = "top-hat"
    try:
        nb_mode = bool(cfg("photometry", "nb_mode"))
    except Exception:
        nb_mode = False
    if nb_mode:
        curves = []
        for k in ("r", "g", "b")[:nc]:
            wl = float(cfg("photometry", f"{k}_wl") or 656.28)
            bw = float(cfg("photometry", f"{k}_bw") or NB_DEFAULT_BW)
            curves.append(tophat_curve(wl - bw / 2, wl + bw / 2))
        report.warn("Siril's SPCC preferences are in narrowband mode: the channel responses "
                    "are top-hats at the stated lines; the result depends on the stated "
                    "bandwidths (spec 15.1 I15).")
        return np.array(curves), "narrowband top-hats (SPCC nb_mode)", True
    line = detect_narrowband_filter(filter_kw) if nc == 1 else None
    if line is not None:
        report.warn(f"FILTER '{filter_kw}' looks like narrowband ({line:.1f} nm): using a "
                    f"{NB_DEFAULT_BW:.0f} nm top-hat; the result depends on the real bandwidth.")
        return tophat_curve(line - NB_DEFAULT_BW / 2, line + NB_DEFAULT_BW / 2)[None, :], \
            f"{NB_DEFAULT_BW:.0f} nm top-hat at {line:.1f} nm", True
    if nc == 3 and filter_kw and re.search(r"\b(sho|hoo|ha|oiii|sii)\b", filter_kw, re.I):
        report.warn(f"FILTER '{filter_kw}' suggests a palette-mapped narrowband image: "
                    "channel responses are unknown; colour-term fit only.")
    tops = [tophat_curve(600, 700), tophat_curve(500, 600), tophat_curve(400, 500)]
    db = SpccDatabase(spcc_root)
    if nc == 1:
        curves = [tophat_curve(400, 700)]
        if not (filter_kw or "").strip():
            report.info("Mono image without filter information: assuming a 400-700 nm "
                        "luminance response")
    else:
        curves = tops
    if db.entries:
        try:
            is_mono = bool(cfg("photometry", "is_mono"))
            if nc == 3 and is_mono:
                qe = db.curve(db.find(cfg("photometry", "monosensorpref")))
                fl = [db.curve(db.find(cfg("photometry", k)))
                      for k in ("redpref", "greenpref", "bluepref")]
                if all(f is not None for f in fl):
                    curves = [f * (qe if qe is not None else 1.0) for f in fl]
                    desc = "SPCC mono filters %s/%s/%s" % tuple(
                        cfg("photometry", k) for k in ("redpref", "greenpref", "bluepref"))
            elif nc == 3:
                sens = cfg("photometry", "oscsensorpref")
                sc = [db.curve(db.find(sens, ch)) for ch in ("RED", "GREEN", "BLUE")]
                if all(c is not None for c in sc):
                    flt = db.curve(db.find(cfg("photometry", "oscfilterpref")))
                    lpf = db.curve(db.find(cfg("photometry", "lpfpref"))) \
                        if bool(cfg("photometry", "is_dslr")) else None
                    curves = [c * (flt if flt is not None else 1.0) * (lpf if lpf is not None else 1.0)
                              for c in sc]
                    desc = f"SPCC OSC sensor {sens}"
            elif nc == 1 and is_mono:
                qe = db.curve(db.find(cfg("photometry", "monosensorpref")))
                if qe is not None:
                    curves = [tophat_curve(400, 700) * qe]
                    desc = "400-700 nm x SPCC mono sensor QE"
        except Exception as e:
            report.info(f"SPCC curves unavailable ({e}); using top-hats")
    curves = np.array([c if c is not None and np.sum(c) > 0 else t
                       for c, t in zip(curves, (tops if nc == 3 else [tophat_curve(400, 700)]))])
    return curves, desc, nb


class SyntheticPhotometry:
    """XP -> S_c and kappa; kappa(Teff); G + kappa -> S_c (spec 4.5)."""

    T_BLUE = tophat_curve(400, 500)
    T_RED = tophat_curve(600, 700)
    T_G = tophat_curve(330, 1050)   # SPEC: rough G stand-in, only for the fallback slope
    # SPEC (round 15): Johnson B, V and Cousins I (Bessell 1990) on the XP grid, and the AB
    # spectrum (W m^-2 nm^-1) that sets their zero points before JC_STANDARD
    T_JC = {k: np.interp(XP_WL, w0 + 10.0 * np.arange(len(v)), v, left=0.0, right=0.0)
            for k, (w0, v) in BESSELL_BVI.items()}
    F_AB = 3.631e-23 * 2.99792458e17 / XP_WL ** 2

    def __init__(self, curves, report):
        self.curves = np.asarray(curves, float)
        self.nc = self.curves.shape[0]
        self.report = report
        self.kt_coef = None
        self.kt_range = (3.45, 4.6)
        self.g_coef = None
        self.hip_rel = None
        self.hip_note = ""
        self.prior_sig = None
        self.alt_ratio = None

    def s_from_spectrum(self, f, curves=None):
        c = self.curves if curves is None else curves
        return (np.asarray(f, float) * XP_WL[None, :] * 2.0) @ c.T

    def kappa_from_spectrum(self, f):
        sb = self.s_from_spectrum(f, self.T_BLUE[None, :])[:, 0]
        sr = self.s_from_spectrum(f, self.T_RED[None, :])[:, 0]
        with np.errstate(all="ignore"):
            return -2.5 * np.log10(sb / sr)

    def blackbody_kappa(self, teff):
        return self.kappa_from_spectrum(planck_lambda(XP_WL, np.atleast_1d(teff)))

    def fit_kappa_teff(self, kappa, teff):
        ok = np.isfinite(kappa) & np.isfinite(teff) & (teff > 2000)
        if ok.sum() >= 20:
            X = np.vander(np.log10(teff[ok]) - 3.8, 3)
            coef, _, keep, _ = robust_linear_fit(X, kappa[ok])
            self.kt_coef = coef
            lt = np.log10(teff[ok][keep])
            self.kt_range = (float(np.percentile(lt, 2)), float(np.percentile(lt, 98)))
            self.report.info(f"kappa(Teff) fitted on {int(keep.sum())} stars with XP and Teff")
        else:
            self.kt_coef = None
            self.report.info("kappa(Teff): fewer than 20 stars with XP and Teff; "
                             "using the blackbody relation")

    def kappa_of_teff(self, teff):
        teff = np.asarray(teff, float)
        out = np.full(teff.shape, np.nan)
        ok = np.isfinite(teff) & (teff > 2000)
        if not np.any(ok):
            return out
        if self.kt_coef is not None:
            # SPEC: the quadratic is only used inside the Teff range it was
            # fitted on; beyond it the blackbody relation continues it,
            # offset to join continuously (hot D stars such as zeta Ori A lie
            # far outside a field fit and a quadratic extrapolates badly).
            lo, hi = self.kt_range
            lt = np.log10(np.clip(teff[ok], 2000, 60000))
            ltc = np.clip(lt, lo, hi)
            k_in = np.polyval(self.kt_coef, ltc - 3.8)
            bb = self.blackbody_kappa(10 ** lt)
            bb_edge = self.blackbody_kappa(10 ** ltc)
            out[ok] = np.where((lt < lo) | (lt > hi), k_in + (bb - bb_edge), k_in)
        else:
            out[ok] = self.blackbody_kappa(np.clip(teff[ok], 2500, 40000))
        return out

    def fit_g_relation(self, g, kappa, S):
        """-2.5 log10 S_c - G = a_c + b_c kappa + c_c kappa^2."""
        ok = np.isfinite(g) & np.isfinite(kappa) & np.all(np.isfinite(S) & (S > 0), axis=1)
        coefs = []
        if ok.sum() >= 20:
            X = np.vander(kappa[ok], 3)
            for c in range(self.nc):
                y = -2.5 * np.log10(S[ok, c]) - g[ok]
                coef, _, _, _ = robust_linear_fit(X, y)
                coefs.append(coef)
            self.report.info(f"G+kappa -> S_c relation fitted on {int(ok.sum())} XP stars")
        else:
            # SPEC: with no XP stars the relation comes from blackbodies through
            # a broad G stand-in; its constant is absorbed by the zero point.
            t = np.geomspace(3000, 30000, 60)
            bb = planck_lambda(XP_WL, t)
            k = self.kappa_from_spectrum(bb)
            sg = self.s_from_spectrum(bb, self.T_G[None, :])[:, 0]
            sc = self.s_from_spectrum(bb)
            X = np.vander(k, 3)
            for c in range(self.nc):
                y = -2.5 * np.log10(sc[:, c] / sg)
                coefs.append(np.linalg.lstsq(X, y, rcond=None)[0])
            self.report.info("G+kappa -> S_c relation from blackbodies (no XP stars)")
        self.g_coef = np.array(coefs)

    def s_from_g(self, g, kappa):
        X = np.vander(np.asarray(kappa, float), 3)
        m = X @ self.g_coef.T + np.asarray(g, float)[:, None]
        return 10.0 ** (-0.4 * m)

    # -- SPEC (round 15): route B ------------------------------------------
    def johnson_from_spectrum(self, f):
        """Standardised synthetic Johnson V, B-V and Cousins V-I of XP spectra:
        energy integration of the Bessell (1990) passbands against the AB
        spectrum, then the JC_STANDARD polynomials in the synthetic B-V."""
        f = np.asarray(f, float)
        m = {}
        with np.errstate(all="ignore"):
            for k, t in self.T_JC.items():
                m[k] = -2.5 * np.log10(np.maximum(f @ t, 1e-300) / float(self.F_AB @ t))
        bv = m["B"] - m["V"]
        return (m["V"] + np.polyval(JC_STANDARD["V"], bv), bv + np.polyval(JC_STANDARD["B-V"], bv),
                m["V"] - m["I"] + np.polyval(JC_STANDARD["V-I"], bv))

    @staticmethod
    def hip_design(bv, vi):
        bv, vi = np.asarray(bv, float), np.asarray(vi, float)
        return np.column_stack([np.ones_like(bv), bv, vi, bv * bv, bv * vi, vi * vi])

    def fit_hip_relation(self, f, g):
        """-2.5 log10 S_c - V and kappa as quadratics in (B-V, V-I), fitted on the
        field's XP stars fainter than HIP_REL_GMIN (their synthetic Johnson-Cousins
        photometry). Sets self.hip_rel (None if too few stars); returns the count."""
        self.hip_rel = None
        if f.shape[0] == 0:
            return 0
        V, BV, VI = self.johnson_from_spectrum(f)
        S = self.s_from_spectrum(f)
        kap = self.kappa_from_spectrum(f)
        # the colour window drops broken spectra (one bubble-rgb XP star had B-V = -7000),
        # which would otherwise be leverage points of the quadratic
        with np.errstate(invalid="ignore"):
            ok = ((g > HIP_REL_GMIN) & (BV > -0.6) & (BV < 3.0) & (VI > -0.6) & (VI < 5.0)
                  & np.isfinite(V) & np.isfinite(kap) & np.all(np.isfinite(S) & (S > 0), axis=1))
        n = int(ok.sum())
        if n < HIP_REL_MIN_STARS:
            return n
        X = self.hip_design(BV[ok], VI[ok])
        coef, mad_ = [], []
        for c in range(self.nc):
            cf, _, keep, res = robust_linear_fit(X, -2.5 * np.log10(S[ok, c]) - V[ok])
            coef.append(cf)
            mad_.append(mad_sigma(res[keep]))
        kcoef, _, _, _ = robust_linear_fit(X, kap[ok])
        self.hip_rel = {"coef": np.array(coef), "kcoef": kcoef, "mad": np.array(mad_), "n": n,
                        "bv_range": (float(np.percentile(BV[ok], 2)), float(np.percentile(BV[ok], 98)))}
        return n

    def s_from_hip(self, table, idx):
        """Route B for the table rows idx: S_c from V and the colour relation, kappa,
        and the prior width sigma_c (mag) from the error terms: V, B-V and V-I errors
        through the relation's gradient, the relation's scatter in this field, the
        route's systematics, colour extrapolation, variability and multiplicity."""
        r = self.hip_rel
        V, bv, vi = table.vmag[idx], table.bv[idx], table.vi[idx]
        X = self.hip_design(bv, vi)
        S = 10.0 ** (-0.4 * (V[:, None] + X @ r["coef"].T))
        kappa = X @ r["kcoef"]
        c = r["coef"]
        dbv = c[None, :, 1] + 2 * c[None, :, 3] * bv[:, None] + c[None, :, 4] * vi[:, None]
        dvi = c[None, :, 2] + c[None, :, 4] * bv[:, None] + 2 * c[None, :, 5] * vi[:, None]
        lo, hi = r["bv_range"]
        ext = HIP_EXTRAP * np.maximum(0.0, np.maximum(lo - bv, bv - hi))
        ebv = np.nan_to_num(table.ebv[idx], nan=0.05)
        evi = np.nan_to_num(table.evi[idx], nan=0.05)
        var = (HIP_V_ERR ** 2 + (dbv * ebv[:, None]) ** 2 + (dvi * evi[:, None]) ** 2 + r["mad"][None, :] ** 2
               + HIP_SYS ** 2 + (ext ** 2 + np.nan_to_num(table.sig_var[idx]) ** 2
                                 + np.nan_to_num(table.sig_mult[idx]) ** 2)[:, None])
        return S, kappa, np.sqrt(var)

    def compute(self, table, allow_hip=True):
        """Return (kappa[n], S[n, nc], colour[n] in {'xp','teff','hip','none'}).
        SPEC (round 15): table stars with Hipparcos photometry take route B
        (colour 'hip', prior widths in self.prior_sig) when the colour relation
        can be fitted; otherwise they keep the XP or Teff route."""
        n = len(table)
        kappa = np.full(n, np.nan)
        S = np.full((n, self.nc), np.nan)
        colour = np.full(n, "none", dtype="<U4")
        hx = table.xp_row >= 0
        if np.any(hx):
            f = table.xp[table.xp_row[hx]]
            S[hx] = self.s_from_spectrum(f)
            kappa[hx] = self.kappa_from_spectrum(f)
            bad = ~np.all(np.isfinite(S[hx]) & (S[hx] > 0), axis=1) | ~np.isfinite(kappa[hx])
            idx = np.nonzero(hx)[0]
            S[idx[bad]] = np.nan
            kappa[idx[bad]] = np.nan
            colour[idx[~bad]] = "xp"
        hx = colour == "xp"
        self.fit_kappa_teff(kappa[hx], table.teff[hx])
        self.fit_g_relation(table.g[hx], kappa[hx], S[hx])
        kt = self.kappa_of_teff(table.teff)
        use_t = (~hx) & np.isfinite(kt)
        kappa[use_t] = kt[use_t]
        colour[use_t] = "teff"
        med = np.nanmedian(kappa) if np.any(np.isfinite(kappa)) else 0.0
        none = ~np.isfinite(kappa)
        kappa[none] = med
        rest = colour != "xp"
        if np.any(rest):
            S[rest] = self.s_from_g(table.g[rest], kappa[rest])
        self.prior_sig = np.full((n, self.nc), np.nan)
        self.alt_ratio = np.full((n, self.nc), np.nan)
        hb = (table.hip >= 0) & np.isfinite(table.vmag) & np.isfinite(table.bv) & np.isfinite(table.vi)
        self.hip_rel = None
        if np.any(hb):
            if not allow_hip:
                self.hip_note = "narrowband channel responses"
            else:
                nrel = self.fit_hip_relation(table.xp[table.xp_row[hx]], table.g[hx])
                if self.hip_rel is None:
                    self.hip_note = f"only {nrel} XP stars with G > {HIP_REL_GMIN:.0f}"
            if self.hip_rel is not None:
                idx = np.nonzero(hb)[0]
                # SPEC (round 17): where XP is also valid (G >= ALT_ROUTE_GMIN), keep
                # S_A / S_B as the second route of the unrefined bound
                had = (colour[idx] == "xp") & (table.g[idx] >= ALT_ROUTE_GMIN)
                S_A = S[idx].copy()
                S[idx], kappa[idx], self.prior_sig[idx] = self.s_from_hip(table, idx)
                with np.errstate(all="ignore"):
                    self.alt_ratio[idx[had]] = S_A[had] / S[idx[had]]
                colour[idx] = "hip"
        return kappa, S, colour


# ===========================================================================
# 7. Photometric calibration (spec 7)
# ===========================================================================

def aperture_fluxes(img_c, xs, ys, r_ap_px, mode, ann=(5.0, 8.0), fwhm_px=3.0,
                    sky_fn=None, lin=None):
    """Aperture photometry of the stars at (xs, ys).
    mode "annulus": local median in an annulus at ann[0]..ann[1] FWHM (pass 0);
    mode "sky": sky_fn(y0, y1, x0, x1) returns the local sky image to subtract
    (pass 1: bg + res + other stars' glow^(0)).
    Returns (flux, n_ap, peak_max) arrays."""
    h, w = img_c.shape
    n = xs.size
    flux = np.full(n, np.nan)
    nap = np.zeros(n)
    peak = np.full(n, np.nan)
    rout = ann[1] * fwhm_px if mode == "annulus" else r_ap_px
    R = int(math.ceil(max(rout, r_ap_px))) + 1
    for i in range(n):
        x, y = xs[i], ys[i]
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        ix, iy = int(round(x)), int(round(y))
        x0, x1 = max(0, ix - R), min(w, ix + R + 1)
        y0, y1 = max(0, iy - R), min(h, iy + R + 1)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        cut = img_c[y0:y1, x0:x1].astype(np.float64)
        Y, X = np.mgrid[y0:y1, x0:x1]
        rr = np.hypot(X - x, Y - y)
        ap = rr <= r_ap_px
        if mode == "annulus":
            an = (rr >= ann[0] * fwhm_px) & (rr <= ann[1] * fwhm_px) & np.isfinite(cut) & (cut != 0)
            if an.sum() < 10:
                continue
            sky = np.median(cut[an])
            v = cut[ap] - sky
        else:
            v = (cut - sky_fn(y0, y1, x0, x1))[ap]
        if not np.all(np.isfinite(v)) or np.any(cut[ap] == 0):
            continue
        flux[i] = float(np.sum(v))
        nap[i] = ap.sum()
        peak[i] = float(np.max(cut[ap]))
    return flux, nap, peak


@dataclass
class Calibration:
    zp: np.ndarray            # (nc,)
    k: np.ndarray             # (nc,)
    kappa0: float
    sigma_agree: np.ndarray   # (nc,)
    n_stars: np.ndarray       # (nc,)
    beta: float = float("nan")
    beta_err: float = float("nan")
    beta_note: str = ""

    def predict(self, S, kappa):
        dk = np.asarray(kappa, float) - self.kappa0
        m = -2.5 * np.log10(np.maximum(S, 1e-300)) + self.zp[None, :] + self.k[None, :] * dk[:, None]
        return 10.0 ** (-0.4 * m)


def fit_calibration(F_meas, S, kappa, good, snr, report, with_slope=False, label="pass 1"):
    """m_inst - m_syn = ZP_c + k_c (kappa - kappa0), Huber then 3 sigma
    clipping; agreement and (optionally) the linearity slope (spec 7)."""
    nc = S.shape[1]
    kappa0 = float(np.median(kappa[np.any(good, axis=1)])) if np.any(good) else 0.0
    zp = np.zeros(nc)
    kk = np.zeros(nc)
    sa = np.full(nc, np.nan)
    ns = np.zeros(nc, int)
    betas = []
    beta_errs = []
    notes = []
    for c in range(nc):
        ok = good[:, c] & (F_meas[:, c] > 0) & (S[:, c] > 0)
        if ok.sum() < 3:
            continue
        m_inst = -2.5 * np.log10(F_meas[ok, c])
        m_syn = -2.5 * np.log10(S[ok, c])
        dk = kappa[ok] - kappa0
        X = np.column_stack([np.ones(ok.sum()), dk])
        coef, cov, keep, res = robust_linear_fit(X, m_inst - m_syn)
        zp[c], kk[c] = coef
        sa[c] = mad_sigma(res[keep])
        ns[c] = int(keep.sum())
        if with_slope:
            y = m_inst - kk[c] * dk
            s_ok = snr[ok, c] > SNR_SLOPE
            use = s_ok if (s_ok.sum() >= 20 and np.ptp(m_syn[s_ok]) >= I4_MIN_SPAN) else np.ones(ok.sum(), bool)
            if np.ptp(m_syn[use]) < I4_MIN_SPAN:
                notes.append(f"span {np.ptp(m_syn[use]):.1f} mag")
                continue
            Xs = np.column_stack([m_syn[use], np.ones(use.sum())])
            cb, cvb, kb, _ = robust_linear_fit(Xs, y[use])
            betas.append(cb[0])
            beta_errs.append(math.sqrt(cvb[0, 0]) if np.isfinite(cvb[0, 0]) else float("nan"))
    cal = Calibration(zp=zp, k=kk, kappa0=kappa0, sigma_agree=sa, n_stars=ns)
    if with_slope:
        if betas:
            cal.beta = float(np.median(betas))
            cal.beta_err = float(np.nanmedian(beta_errs))
        else:
            cal.beta_note = "not measurable (" + (", ".join(notes) or "too few stars") + ")"
    return cal


# ===========================================================================
# 5. Image geometry (spec 5)
# ===========================================================================
#
# Conventions (verified):
#  * pixel arrays are in FITS storage order: arr[..., j, i] <-> astropy pixel
#    (x=i, y=j), origin 0, no flip;
#  * PSFStar.xpos/ypos from findstar are in Siril's DISPLAY frame (rows
#    top-down: star_finder.c builds its row pointers flipped) with a
#    pixel-corner origin: astropy0 x = xpos - 0.5, astropy0 y = ry - ypos - 0.5
#    (ry = image height). This matches Siril's own astrometry.net export,
#    X = xpos + 0.5, Y = ry - ypos + 0.5 (FITS 1-based). SPEC: the spec's
#    "astropy0 = (xpos - 0.5, ypos - 0.5)" was right for x only (found in live
#    Siril testing). PSFStar.angle is not used, so its sign flip does not matter;
#  * sirilpy pix2radec/radec2pix use flipped display coordinates and are
#    not used anywhere in this script.

@dataclass
class Detection:
    x: float            # astropy 0-based, FITS storage order
    y: float
    fwhm: float         # px, mean of fwhmx and fwhmy
    roundness: float
    peak: float         # amplitude above background, image units [0, 1]
    saturated: bool
    sat: float          # PSFStar.sat converted to [0, 1]
    channel: int = 0


def psfstar_to_detection(p, unit_scale, channel, ry):
    """Convert a sirilpy PSFStar (display frame, see the conventions above)
    to FITS storage order. unit_scale converts native units to [0, 1]; ry is
    the image height in pixels."""
    fx = float(getattr(p, "fwhmx", 0.0) or 0.0)
    fy = float(getattr(p, "fwhmy", 0.0) or 0.0)
    fw = 0.5 * (fx + fy) if fx > 0 and fy > 0 else max(fx, fy)
    rnd = (min(fx, fy) / max(fx, fy)) if fx > 0 and fy > 0 else 1.0
    return Detection(x=float(p.xpos) - 0.5, y=float(ry) - float(p.ypos) - 0.5, fwhm=fw, roundness=rnd,
                     peak=float(getattr(p, "A", 0.0) or 0.0) * unit_scale,
                     saturated=bool(getattr(p, "has_saturated", False)),
                     sat=float(getattr(p, "sat", 0.0) or 0.0) * unit_scale, channel=channel)


class ImageGeometry:
    """WCS with SIP inside the frame and the linear part outside."""

    def __init__(self, header, shape):
        from astropy.wcs import WCS
        from astropy.io import fits
        self.h, self.w = shape
        hdr = fits.Header()
        for k, v in header.items():
            if k in ("COMMENT", "HISTORY", "") or k.startswith("HIERARCH"):
                continue
            try:
                hdr[k] = v
            except Exception:
                continue
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.wcs = WCS(hdr, naxis=2, relax=True)
        self.has_sip = self.wcs.sip is not None
        cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0
        self.J = self.local_jacobian(cx, cy)      # arcsec per px (2x2)
        self.M = self.J.T @ self.J
        self.A_px = abs(float(np.linalg.det(self.J)))
        self.scale = math.sqrt(self.A_px)
        self.center = self.pix2world(np.array([cx]), np.array([cy]))
        corners = self.pix2world(np.array([-0.5, self.w - 0.5, -0.5, self.w - 0.5]),
                                 np.array([-0.5, -0.5, self.h - 0.5, self.h - 0.5]))
        self.half_diag_deg = float(np.max(angular_sep_deg(self.center[0][0], self.center[1][0],
                                                          corners[0], corners[1])))
        self.band_px = BORDER_BAND * max(self.w, self.h)

    def local_jacobian(self, x, y, d=1.0):
        """d(world)/d(pixel) at (x, y) in arcsec/px, with the RA axis scaled
        by cos(dec) so that the metric is Euclidean on the sky."""
        ra, dec = self.pix2world(np.array([x, x + d, x]), np.array([y, y, y + d]))
        dra = ((ra[1:] - ra[0] + 180.0) % 360.0) - 180.0
        ddec = dec[1:] - dec[0]
        c = math.cos(math.radians(dec[0]))
        J = np.array([[dra[0] * c, dra[1] * c], [ddec[0], ddec[1]]]) * 3600.0 / d
        return J

    def pix2world(self, x, y):
        r, d = self.wcs.all_pix2world(np.asarray(x, float), np.asarray(y, float), 0)
        return np.asarray(r), np.asarray(d)

    def world2pix(self, ra, dec):
        """Linear projection for all stars; full WCS (SIP) re-projection only
        for stars within the frame plus the border band, blended over it."""
        ra = np.asarray(ra, float)
        dec = np.asarray(dec, float)
        if ra.size == 0:
            return np.zeros(0), np.zeros(0)
        x, y = self.wcs.wcs_world2pix(ra, dec, 0)
        x, y = np.asarray(x, float), np.asarray(y, float)
        # stars far behind the tangent plane give garbage: push them away
        sep = angular_sep_deg(self.center[0][0], self.center[1][0], ra, dec)
        far = sep > 80.0
        x[far] = np.inf
        y[far] = np.inf
        if not self.has_sip:
            return x, y
        dout = self.outside_distance_px(x, y)
        near = np.isfinite(dout) & (dout < self.band_px)
        if np.any(near):
            try:
                xf, yf = self.wcs.all_world2pix(ra[near], dec[near], 0, quiet=True,
                                                maxiter=50, tolerance=1e-4)
                wfull = 1.0 - np.clip(dout[near] / self.band_px, 0, 1)
                ok = np.isfinite(xf) & np.isfinite(yf)
                xn, yn = x[near], y[near]
                xn[ok] = wfull[ok] * xf[ok] + (1 - wfull[ok]) * xn[ok]
                yn[ok] = wfull[ok] * yf[ok] + (1 - wfull[ok]) * yn[ok]
                x[near], y[near] = xn, yn
            except Exception:
                pass
        return x, y

    def outside_distance_px(self, x, y):
        dx = np.maximum(np.maximum(-0.5 - x, x - (self.w - 0.5)), 0)
        dy = np.maximum(np.maximum(-0.5 - y, y - (self.h - 0.5)), 0)
        return np.hypot(dx, dy)

    def r_arcsec(self, dx, dy):
        M = self.M
        return np.sqrt(np.maximum(M[0, 0] * dx * dx + 2 * M[0, 1] * dx * dy + M[1, 1] * dy * dy, 0))

    def frame_distance_arcsec(self, x, y):
        """Distance from (x, y) to the nearest point of the frame (0 inside)."""
        cxp = np.clip(x, -0.5, self.w - 0.5)
        cyp = np.clip(y, -0.5, self.h - 0.5)
        return self.r_arcsec(x - cxp, y - cyp)

    def in_frame(self, x, y, margin_px=0.0):
        ok = ((x >= margin_px - 0.5) & (x <= self.w - 0.5 - margin_px)
              & (y >= margin_px - 0.5) & (y <= self.h - 0.5 - margin_px))
        sat = getattr(self, "fill_sat", None)
        if sat is None:
            return ok
        # SPEC (round 7): an empty (fill) border counts as outside the frame:
        # a position is in frame only if no fill pixel lies within margin_px
        xa, ya = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        oka = np.atleast_1d(ok).copy()
        fin = oka & np.isfinite(xa) & np.isfinite(ya)
        if np.any(fin):
            m = max(float(margin_px), 0.0)
            xi, yi = np.rint(xa[fin]).astype(np.int64), np.rint(ya[fin]).astype(np.int64)
            x0 = np.clip(xi - int(math.ceil(m)), 0, self.w)
            x1 = np.clip(xi + int(math.ceil(m)) + 1, 0, self.w)
            y0 = np.clip(yi - int(math.ceil(m)), 0, self.h)
            y1 = np.clip(yi + int(math.ceil(m)) + 1, 0, self.h)
            cnt = sat[y1, x1] - sat[y0, x1] - sat[y1, x0] + sat[y0, x0]
            oka[np.nonzero(fin)[0][cnt > 0]] = False
        return oka if np.ndim(ok) else bool(oka[0])

    def set_fill(self, mask):
        """SPEC (round 7): register the empty-border mask (h, w) of all channels."""
        if mask is None or not np.any(mask):
            self.fill_sat = None
            return
        sat = np.zeros((self.h + 1, self.w + 1), np.int32)
        sat[1:, 1:] = np.cumsum(np.cumsum(mask, axis=0, dtype=np.int32), axis=1, dtype=np.int32)
        self.fill_sat = sat

    def px_extent(self, r_arcsec):
        """Half-size in px of a box containing the ellipse r <= r_arcsec."""
        Minv = np.linalg.inv(self.M)
        return (float(r_arcsec) * math.sqrt(Minv[0, 0]), float(r_arcsec) * math.sqrt(Minv[1, 1]))


BORDER_MIN_DEPTH = 3          # SPEC (round 6): fill borders deeper than this (px) are warned
BORDER_EDGE_MODE_FRAC = 0.25  # an exact value covering this share of the frame edge is a fill candidate
BORDER_INTERIOR_MAX = 0.005   # ... unless it also covers this share of the interior (clipped data)


def _edge_runs(fill):
    """Inward run lengths of fill pixels from each edge: per row from the
    left/right, per column from the bottom/top (FITS rows). A row or
    column that is entirely fill has run = its length."""
    h, w = fill.shape

    def runs(m):
        nz = ~m
        r = np.argmax(nz, axis=1)
        r[~nz.any(axis=1)] = m.shape[1]
        return r
    return runs(fill), runs(fill[:, ::-1]), runs(fill.T), runs(fill.T[:, ::-1])


def valid_box(inv):
    """Largest axis-aligned rectangle free of invalid pixels, by greedy inward
    shrinking of the boundary line that holds the most invalid pixels
    (exact for border-shaped regions). Returns (x0, x1, y0, y1), half-open."""
    h, w = inv.shape
    x0, x1, y0, y1 = 0, w, 0, h
    for _ in range(2 * (h + w)):
        if x1 - x0 < 2 or y1 - y0 < 2:
            break
        cand = {"left": int(inv[y0:y1, x0].sum()), "right": int(inv[y0:y1, x1 - 1].sum()),
                "bottom": int(inv[y0, x0:x1].sum()), "top": int(inv[y1 - 1, x0:x1].sum())}
        k = max(cand, key=cand.get)
        if cand[k] == 0:
            break
        if k == "left":
            x0 += 1
        elif k == "right":
            x1 -= 1
        elif k == "bottom":
            y0 += 1
        else:
            y1 -= 1
    return x0, x1, y0, y1


def detect_fill_borders(data, names=None):
    """SPEC (round 6): per channel, the frame-edge regions holding an exact
    fill value (0, NaN or another exact constant), e.g. from compositing
    unaligned mono stacks or from registration. Cheap: one exact-value mode
    on the frame edge, then inward runs per row and column (handles straight
    edges, rotation wedges and partial edges). A candidate value that also
    fills more than 0.5% of the interior is real (clipped) data, not a fill.
    Returns a dict: channels (per channel: fill value, depth per edge in px,
    affected fraction), box (x0, x1, y0, y1) valid in all channels (FITS
    pixels, half-open), depth (max inward extent over channels), crop (the
    Siril `crop` arguments in display coordinates), and differs (the
    channels' valid areas differ)."""
    arr = data if data.ndim == 3 else data[None]
    nc, h, w = arr.shape
    names = names or (["L"] if nc == 1 else ["R", "G", "B"][:nc] if nc <= 3 else [str(c) for c in range(nc)])
    xx = np.arange(w)[None, :]
    yy = np.arange(h)[:, None]
    inv_any = np.zeros((h, w), bool)
    masks, out = [], []
    for c in range(nc):
        a = arr[c]
        edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        nanf = ~np.isfinite(edge)
        fv = None
        if nanf.sum() >= BORDER_EDGE_MODE_FRAC * edge.size / 4:
            fv = "nan"
        else:
            vals, cnt = np.unique(edge[~nanf], return_counts=True)
            if cnt.size and cnt.max() >= BORDER_EDGE_MODE_FRAC * edge.size / 4:
                fv = float(vals[np.argmax(cnt)])
        if fv is None:
            masks.append(None)
            out.append({"name": names[c], "fill": None, "depth": {}, "fraction": 0.0})
            continue
        fill = ~np.isfinite(a) if fv == "nan" else (a == np.float32(fv)) | ~np.isfinite(a)
        L, Rr, B, T = _edge_runs(fill)
        inv = (xx < L[:, None]) | (xx >= w - Rr[:, None]) | (yy < B[None, :]) | (yy >= h - T[None, :])
        interior = fill & ~inv
        nval = max(1, int((~inv).sum()))
        if interior.sum() > BORDER_INTERIOR_MAX * nval:
            masks.append(None)
            out.append({"name": names[c], "fill": None, "depth": {}, "fraction": 0.0,
                        "note": "edge value also common inside (clipped data, not a fill)"})
            continue

        bx0, bx1, by0, by1 = valid_box(inv)
        dep = {"left": bx0, "right": w - bx1, "bottom": by0, "top": h - by1}
        masks.append(inv)
        inv_any |= inv
        out.append({"name": names[c], "fill": fv, "depth": dep, "fraction": float(inv.mean())})
    x0, x1, y0, y1 = valid_box(inv_any)
    differs = False
    if nc > 1:
        ms = [m if m is not None else np.zeros((h, w), bool) for m in masks]
        differs = any(np.any(ms[c] != ms[0]) for c in range(1, nc))
    dmax = max([max(o["depth"].values()) if o["depth"] else 0 for o in out] + [0])
    return {"channels": out, "box": (x0, x1, y0, y1), "depth": dmax, "differs": differs,
            "crop": (x0, h - y1, x1 - x0, y1 - y0), "shape": (h, w), "fraction": float(inv_any.mean()),
            "mask": inv_any}


def describe_fill_borders(res):
    """Message text for detect_fill_borders(); None if there is no border."""
    if res is None or res["depth"] == 0:
        return None
    parts = []
    for o in res["channels"]:
        d = {k: v for k, v in o["depth"].items() if v > 0}
        if not d:
            continue
        fill = "NaN" if o["fill"] == "nan" else ("0" if o["fill"] == 0 else f"constant {o['fill']:.4g}")
        sides = ", ".join(f"{k} {v} px" for k, v in d.items())
        parts.append(f"{o['name']} empty ({fill}) on {sides}")
    x, y, cw, ch = res["crop"]
    what = ("Channels have unaligned empty borders" if res["differs"] else
            "The image has empty borders")
    return (f"{what} ({'; '.join(parts)}; {100 * res['fraction']:.1f}% of the frame). The empty "
            f"pixels bias the background, calibration and colour. Crop to the common area first, e.g. "
            f"crop {x} {y} {cw} {ch}")


def fingerprint_rows(h):
    """Array rows (numpy order) whose statistics make the fingerprint."""
    return [min(int(h * f), h - 1) for f in (0.1, 0.3, 0.5, 0.7, 0.9)]


def fingerprint_from_rows(rows, shape, filename):
    """SPEC (round 19): the fingerprint from the fingerprint rows alone,
    rows[c, k] = array row fingerprint_rows(h)[k] of channel c."""
    nc, h, w = shape
    st = []
    for c in range(nc):
        for k in range(rows.shape[1]):
            v = rows[c, k].astype(np.float64)
            st.append([float(np.nanmean(v)), float(np.nanstd(v))])
    return {"filename": os.path.basename(filename or ""), "shape": [int(nc), int(h), int(w)],
            "rows": st}


def image_fingerprint(data, filename):
    """Cheap fingerprint (spec 15.3 R3): filename, shape and row statistics."""
    arr = data if data.ndim == 3 else data[None]
    return fingerprint_from_rows(arr[:, fingerprint_rows(arr.shape[1])], arr.shape, filename)


def fingerprints_match(a, b, rtol=1e-5):
    if not a or not b:
        return False
    if a.get("shape") != b.get("shape") or a.get("filename") != b.get("filename"):
        return False
    ra, rb = np.array(a.get("rows", [])), np.array(b.get("rows", []))
    return ra.shape == rb.shape and np.allclose(ra, rb, rtol=rtol, atol=1e-7)


def saturation_level(img_c, dets_c):
    """sat_c (spec 5): min PSFStar.sat over saturated detections, else the
    clipping plateau, else 1.0."""
    sats = [d.sat for d in dets_c if d.saturated and d.sat > 0]
    if sats:
        return float(min(sats)), "saturated detections"
    m = float(np.nanmax(img_c))
    if m > 0:
        n_at = int(np.count_nonzero(img_c >= m * (1 - 1e-4)))
        if n_at >= 20:
            return m, "histogram plateau"
    return 1.0, "default"


def astrometric_check(geom, xs, ys, g, dets, fwhm):
    """Spec 5 astrometric check. Returns a dict with the match statistics."""
    out = {"n_match": 0, "dx": 0.0, "dy": 0.0, "rms": float("nan"), "fraction": 0.0, "n_ref": 0}
    inside = geom.in_frame(xs, ys) & np.isfinite(xs)
    gi = inside & (g <= 17.0)
    if not dets or not np.any(gi):
        return out
    dx_all = np.array([d.x for d in dets])
    dy_all = np.array([d.y for d in dets])
    unsat = np.array([not d.saturated for d in dets])
    tree = cKDTree(np.column_stack([xs[gi], ys[gi]]))
    dd, jj = tree.query(np.column_stack([dx_all[unsat], dy_all[unsat]]),
                        distance_upper_bound=MATCH_RADIUS_PX)
    ok = np.isfinite(dd)
    if np.any(ok):
        gx, gy = xs[gi][jj[ok]], ys[gi][jj[ok]]
        ox = dx_all[unsat][ok] - gx
        oy = dy_all[unsat][ok] - gy
        mx, my = float(np.median(ox)), float(np.median(oy))
        r = np.hypot(ox - mx, oy - my)
        keep = r <= max(3 * 1.4826 * np.median(r), 0.5)
        out.update(n_match=int(ok.sum()), dx=mx, dy=my,
                   rms=float(np.sqrt(np.mean(r[keep] ** 2))) if np.any(keep) else float("nan"))
    ref = inside & (g <= 14.0) & geom.in_frame(xs, ys, EDGE_FWHM * fwhm)
    out["n_ref"] = int(ref.sum())
    if out["n_ref"]:
        dtree = cKDTree(np.column_stack([dx_all, dy_all]))
        d2, _ = dtree.query(np.column_stack([xs[ref] + out["dx"], ys[ref] + out["dy"]]),
                            distance_upper_bound=MATCH_RADIUS_PX)
        out["fraction"] = float(np.mean(np.isfinite(d2)))
    return out


def saturated_regions(img, lin):
    """Label the connected regions where any channel is >= lin_c."""
    arr = img if img.ndim == 3 else img[None]
    m = np.zeros(arr.shape[1:], bool)
    for c in range(arr.shape[0]):
        m |= arr[c] >= lin[c]
    lab, n = ndimage.label(m)
    return lab, n


def recentre_saturated(lab, n, xs, ys, order, geom):
    """Recentre saturated stars on their region centroid (spec 5); returns
    (x, y, r_sat_px). Bleed-aware: keeps the projected position when the
    centroid is more than 2 px away. Regions are assigned brightest first."""
    x = xs.copy()
    y = ys.copy()
    rsat = np.zeros(xs.size)
    if n == 0:
        return x, y, rsat
    objs = ndimage.find_objects(lab)
    areas = ndimage.sum_labels(np.ones_like(lab, dtype=np.float32), lab, np.arange(1, n + 1))
    used = set()
    h, w = lab.shape
    for i in order:
        if not (np.isfinite(xs[i]) and geom.in_frame(xs[i], ys[i])):
            continue
        ix, iy = int(round(xs[i])), int(round(ys[i]))
        y0, y1 = max(0, iy - 2), min(h, iy + 3)
        x0, x1 = max(0, ix - 2), min(w, ix + 3)
        labs = np.unique(lab[y0:y1, x0:x1])
        labs = [int(v) for v in labs if v > 0 and int(v) not in used]
        if not labs:
            continue
        L = max(labs, key=lambda v: areas[v - 1])
        used.add(L)
        sl = objs[L - 1]
        sub = lab[sl] == L
        yy, xx = np.nonzero(sub)
        cy = yy.mean() + sl[0].start
        cx = xx.mean() + sl[1].start
        rsat[i] = math.sqrt(areas[L - 1] / math.pi)
        if math.hypot(cx - xs[i], cy - ys[i]) <= 2.0:
            x[i], y[i] = cx, cy
    return x, y, rsat


def recentre_on_detections(xs, ys, g, dets, inside, radius=MATCH_RADIUS_PX):
    """SPEC (deviation): place in-frame stars on their matched unsaturated
    detection (Siril's PSF-fit position). Each detection is assigned to the
    brightest catalogue star within `radius`, one to one. The spec defers a
    polynomial astrometric refinement on the assumption of sub-pixel errors;
    real solutions (e.g. a WCS without SIP, or rotated after solving) can be
    off by 1-4 px, which breaks the core rings and misplaces the model cores.
    Returns (x, y, n_moved, median_shift)."""
    x = xs.copy()
    y = ys.copy()
    ud = [d for d in dets if not d.saturated]
    if not ud:
        return x, y, 0, 0.0
    D = np.array([[d.x, d.y] for d in ud])
    tree = cKDTree(D)
    idx = np.nonzero(inside & np.isfinite(xs))[0]
    idx = idx[np.argsort(g[idx])]
    used = set()
    shifts = []
    for i in idx:
        cand = tree.query_ball_point([xs[i], ys[i]], radius)
        cand = [c for c in cand if c not in used]
        if not cand:
            continue
        c = min(cand, key=lambda k: (D[k, 0] - xs[i]) ** 2 + (D[k, 1] - ys[i]) ** 2)
        used.add(c)
        shifts.append(math.hypot(D[c, 0] - xs[i], D[c, 1] - ys[i]))
        x[i], y[i] = D[c]
    return x, y, len(shifts), float(np.median(shifts)) if shifts else 0.0


def astrometric_refinement(xs, ys, g, dets, geom, radius=10.0, gmax=13.5, min_matches=30, apply=True):
    """SPEC (deviation): the polynomial astrometric refinement the spec
    deferred. Bright, isolated, unsaturated Gaia stars are matched to
    detections within `radius` px, and a cubic polynomial in (x, y) is fitted
    robustly to the offsets. It is applied to every star at its position
    clamped to the frame (off-frame stars get the edge correction). Needed when
    a solution has no distortion terms (e.g. SIP dropped by a rotation): errors
    of 5+ px near the edges were seen on real data. Returns (x, y, info)."""
    info = {"n": 0, "rms_before": float("nan"), "rms_after": float("nan"), "applied": False}
    ud = [d for d in dets if not d.saturated]
    inside = geom.in_frame(xs, ys, 10) & np.isfinite(xs)
    if len(ud) < min_matches or inside.sum() < min_matches:
        return xs, ys, info
    D = np.array([[d.x, d.y] for d in ud])
    dtree = cKDTree(D)
    cand = np.nonzero(inside & (g <= gmax))[0]
    gtree = cKDTree(np.column_stack([xs[inside], ys[inside]]))
    gin = g[inside]
    pairs = []
    for i in cand:
        nb = gtree.query_ball_point([xs[i], ys[i]], 1.5 * radius)
        if any(gin[j] < g[i] + 3 and abs(gin[j] - g[i]) > 1e-9 for j in nb):
            continue                      # not isolated
        dn = dtree.query_ball_point([xs[i], ys[i]], radius)
        if len(dn) != 1:
            continue
        pairs.append((i, dn[0]))
    if len(pairs) < min_matches:
        return xs, ys, info
    ii = np.array([p_[0] for p_ in pairs])
    jj = np.array([p_[1] for p_ in pairs])
    off = D[jj] - np.column_stack([xs[ii], ys[ii]])
    u = (xs[ii] - (geom.w - 1) / 2) / (geom.w / 2)
    v = (ys[ii] - (geom.h - 1) / 2) / (geom.h / 2)
    terms = [(a, b) for d in range(4) for a in range(d + 1) for b in [d - a]]
    X = np.column_stack([u ** a * v ** b for a, b in terms])
    cx, _, kx, rx = robust_linear_fit(X, off[:, 0])
    cy, _, ky, ry = robust_linear_fit(X, off[:, 1])
    keep = kx & ky
    info.update(n=int(keep.sum()),
                rms_before=float(np.sqrt(np.mean(np.sum(off[keep] ** 2, axis=1)))),
                rms_after=float(np.sqrt(np.mean(rx[keep] ** 2 + ry[keep] ** 2))))
    info["median_offset"] = (float(np.median(off[keep, 0])), float(np.median(off[keep, 1])))
    if not apply or info["n"] < min_matches or not (info["rms_after"] < info["rms_before"]):
        return xs, ys, info
    info["applied"] = True
    fin = np.isfinite(xs) & np.isfinite(ys)
    xc = np.clip(xs[fin], 0, geom.w - 1)
    yc = np.clip(ys[fin], 0, geom.h - 1)
    U = (xc - (geom.w - 1) / 2) / (geom.w / 2)
    V = (yc - (geom.h - 1) / 2) / (geom.h / 2)
    XX = np.column_stack([U ** a * V ** b for a, b in terms])
    x = xs.copy()
    y = ys.copy()
    x[fin] += XX @ cx
    y[fin] += XX @ cy
    return x, y, info


# ===========================================================================
# 6. Joint background and outer-wing fit (spec 6)
# ===========================================================================

def poly_terms(order):
    return [(i, j) for d in range(order + 1) for i in range(d + 1) for j in [d - i]]


def poly_design(x, y, w, h, order):
    """Polynomial columns at native coordinates, normalised to [-1, 1]."""
    u = (np.asarray(x, float) - (w - 1) / 2.0) / (w / 2.0)
    v = (np.asarray(y, float) - (h - 1) / 2.0) / (h / 2.0)
    return np.column_stack([u ** i * v ** j for i, j in poly_terms(order)])


def eval_poly_image(coef, order, h, w, y0=0, y1=None, x0=0, x1=None):
    """Evaluate the background polynomial on a native-pixel window."""
    y1 = h if y1 is None else y1
    x1 = w if x1 is None else x1
    u = ((np.arange(x0, x1) - (w - 1) / 2.0) / (w / 2.0)).astype(np.float64)
    v = ((np.arange(y0, y1) - (h - 1) / 2.0) / (h / 2.0)).astype(np.float64)
    # SPEC (round 18): summed in float64 over bands of rows (the same operations
    # in the same order per pixel) instead of on two full-frame float64 arrays
    terms = [(c, u ** i, v ** j) for c, (i, j) in zip(coef, poly_terms(order)) if c != 0]
    out = np.empty((y1 - y0, x1 - x0), dtype=np.float32)
    rows = 128
    acc = np.empty((min(rows, y1 - y0), x1 - x0), dtype=np.float64)
    tmp = np.empty_like(acc)
    for a in range(0, y1 - y0, rows):
        b_ = min(y1 - y0, a + rows)
        ac, tm = acc[:b_ - a], tmp[:b_ - a]
        ac[:] = 0.0
        for c, ui, vj in terms:
            np.multiply(vj[a:b_, None], ui[None, :], out=tm)
            tm *= c
            ac += tm
        out[a:b_] = ac
    return out


@dataclass
class WingFit:
    """Result of one joint fit (one channel, or luminance)."""
    poly: np.ndarray
    a: np.ndarray                 # wing coefficients (original scale)
    edges_lo: np.ndarray          # kept annuli [lo, hi) in arcsec
    edges_hi: np.ndarray
    cov_a: np.ndarray
    r_mid: np.ndarray
    p: np.ndarray
    p_sigma: np.ndarray
    n_kept: int
    dof_wing: float
    rms: float
    residual: np.ndarray          # block-scale residual, NaN where not fitted
    usable: bool
    template_amp: float = float("nan")


class JointBackground:
    """Masked block medians, tilted annular bases, annulus-wise pruning,
    ridge lsq_linear with Tukey reweighting (spec 6)."""

    def __init__(self, shape, geom, b, rho0, maxradius, order, report, alpha0=ALPHA0,
                 n_bases=N_WING_BASES, prune=PRUNE_THRESHOLD, ridge=RIDGE_FRACTION):
        self.h, self.w = shape
        self.geom = geom
        self.b = int(b)
        self.rho0 = float(rho0)
        self.maxradius = float(maxradius)
        self.order = int(order)
        self.report = report
        self.alpha0 = alpha0
        self.prune = prune
        self.ridge = ridge
        self.nby, self.nbx = -(-self.h // self.b), -(-self.w // self.b)
        k = n_bases if self.maxradius > 1.6 * self.rho0 else 1
        if k > 1:
            self.edges = np.concatenate([[self.rho0], np.geomspace(1.6 * self.rho0, self.maxradius, k)])
        else:
            self.edges = np.array([self.rho0, max(self.maxradius, 1.01 * self.rho0)])
        self.K = self.edges.size - 1
        yc = (np.arange(self.nby) + 0.5) * self.b - 0.5
        xc = (np.arange(self.nbx) + 0.5) * self.b - 0.5
        yy, xx = np.meshgrid(np.clip(yc, 0, self.h - 1), np.clip(xc, 0, self.w - 1), indexing="ij")
        self.block_x, self.block_y = xx.ravel(), yy.ravel()
        self.P_all = poly_design(self.block_x, self.block_y, self.w, self.h, self.order)

    # -- data --------------------------------------------------------------
    def block_data(self, img_c, valid):
        med, frac = masked_block_median(img_c, valid, self.b)
        return med.ravel().astype(np.float64)

    def subpoints(self, valid):
        """4x4 sub-sample per block; returns (x, y, block_index, weight)
        where the weight averages each basis over the valid sub-samples."""
        q = (np.arange(4) + 0.5) * self.b / 4.0 - 0.5
        by, bx = np.meshgrid(np.arange(self.nby), np.arange(self.nbx), indexing="ij")
        X = (bx[..., None, None] * self.b + q[None, None, None, :]).repeat(4, axis=2)
        Y = (by[..., None, None] * self.b + q[None, None, :, None]).repeat(4, axis=3)
        X = X.reshape(self.nby, self.nbx, 16)
        Y = Y.reshape(self.nby, self.nbx, 16)
        blk = np.broadcast_to((by * self.nbx + bx)[..., None], X.shape)
        xi = np.clip(np.round(X).astype(np.int64), 0, self.w - 1)
        yi = np.clip(np.round(Y).astype(np.int64), 0, self.h - 1)
        inb = (X <= self.w - 0.5) & (Y <= self.h - 0.5)
        ok = inb & valid[yi, xi]
        nvalid = ok.sum(axis=2, keepdims=True)
        ninb = inb.sum(axis=2, keepdims=True)
        wgt = np.where(nvalid > 0, ok / np.maximum(nvalid, 1), inb / np.maximum(ninb, 1))
        sel = wgt > 0
        return X[sel], Y[sel], blk[sel].astype(np.int64), wgt[sel]

    def annulus_images(self, casters_xy, F, valid, pfun=None):
        """D[f, k, block] for every fit f (columns of F). With pfun (template
        mode) a single column sum_i F_i A_px p(r_i) 1[r >= rho0] is built."""
        X, Y, blk, wgt = self.subpoints(valid)
        nb = self.nby * self.nbx
        K = 1 if pfun is not None else self.K
        nfit = F.shape[1]
        D = np.zeros((nfit, K, nb))
        D4 = D.reshape(nfit, K, self.nby, self.nbx)
        # SPEC (round 18): each caster is evaluated only on the sub-points of
        # the blocks inside its maxradius box (about 10% of the frame on M31)
        # instead of on all of them. The sub-points are block-ordered, so the
        # points of a block row of the box are one contiguous run; the kept
        # points enter each block's sum in the same order, so D is unchanged.
        bstart = np.searchsorted(blk, np.arange(nb + 1))
        brow, bcol = blk // self.nbx, blk % self.nbx
        ex, ey = self.geom.px_extent(self.maxradius)
        b = self.b
        for i, (cx, cy) in enumerate(casters_xy):
            if not (np.isfinite(cx) and np.isfinite(cy)):
                continue
            i0 = max(0, int(math.floor((cx - ex) / b)) - 1)
            i1 = min(self.nbx, int(math.floor((cx + ex) / b)) + 2)
            j0 = max(0, int(math.floor((cy - ey) / b)) - 1)
            j1 = min(self.nby, int(math.floor((cy + ey) / b)) + 2)
            if i0 >= i1 or j0 >= j1:
                continue
            rows = np.arange(j0, j1) * self.nbx
            a_, b_ = bstart[rows + i0], bstart[rows + i1]
            lens = b_ - a_
            if lens.sum() == 0:
                continue
            if i0 == 0 and i1 == self.nbx:
                pts = slice(int(a_[0]), int(b_[-1]))     # full-width box: one contiguous run
            else:
                pts = np.repeat(a_ - np.concatenate([[0], np.cumsum(lens)[:-1]]), lens) + np.arange(lens.sum())
            r = self.geom.r_arcsec(X[pts] - cx, Y[pts] - cy)
            sel = (r >= self.rho0) & (r < self.maxradius)
            if not np.any(sel):
                continue
            rr = r[sel]
            if pfun is None:
                k = np.searchsorted(self.edges, rr, side="right") - 1
                k = np.clip(k, 0, K - 1)
                val = self.geom.A_px * (rr / self.rho0) ** (-self.alpha0) * wgt[pts][sel]
            else:
                k = np.zeros(rr.size, np.int64)
                val = self.geom.A_px * pfun(rr) * wgt[pts][sel]
            nj, ni = j1 - j0, i1 - i0
            if isinstance(pts, slice):
                loc = blk[pts][sel] - j0 * self.nbx
            else:
                loc = (brow[pts][sel] - j0) * ni + (bcol[pts][sel] - i0)
            geo = np.bincount(k * (nj * ni) + loc, weights=val, minlength=K * nj * ni).reshape(K, nj, ni)
            for f in range(nfit):
                if F[i, f] != 0:
                    D4[f, :, j0:j1, i0:i1] += F[i, f] * geo
        return D

    # -- pruning -----------------------------------------------------------
    def prune_annuli(self, D, P, sw):
        """Drop annuli whose image the polynomial absorbs (spec 6, CDR).
        Returns (kept D list, lo, hi)."""
        Ps = P * sw[:, None]
        Q, _ = np.linalg.qr(Ps)
        Dk = [D[k].copy() for k in range(D.shape[0])]
        lo = list(self.edges[:-1])
        hi = list(self.edges[1:])
        keep = [True] * len(Dk)
        for k in range(len(Dk) - 1, -1, -1):
            v = Dk[k] * sw
            n0 = np.linalg.norm(v)
            res = v - Q @ (Q.T @ v)
            ratio = np.linalg.norm(res) / n0 if n0 > 0 else 0.0
            if ratio < self.prune:
                keep[k] = False
                j = k - 1
                while j >= 0 and not keep[j]:
                    j -= 1
                if k > 0:
                    # merge into the next annulus inward
                    Dk[k - 1] = Dk[k - 1] + Dk[k]
                    hi[k - 1] = hi[k]
        kept = [i for i in range(len(Dk)) if keep[i]]
        return [Dk[i] for i in kept], np.array([lo[i] for i in kept]), np.array([hi[i] for i in kept])

    # -- one fit -----------------------------------------------------------
    def fit(self, y_all, D_all, template=False):
        ok = np.isfinite(y_all)
        y = y_all[ok]
        P = self.P_all[ok]
        D = D_all[:, ok]
        n, m = P.shape
        w = np.ones(n)
        result = None
        for it in range(TUKEY_ITER + 1):
            sw = np.sqrt(w)
            if template:
                Dk = [D[0]]
                lo, hi = np.array([self.rho0]), np.array([self.maxradius])
                if np.linalg.norm(D[0]) == 0:
                    Dk, lo, hi = [], np.zeros(0), np.zeros(0)
            else:
                Dk, lo, hi = self.prune_annuli(D, P, sw)
            Kk = len(Dk)
            B = np.cumsum(np.array(Dk), axis=0).T if Kk else np.zeros((n, 0))
            X = np.hstack([P, B])
            Xw = X * sw[:, None]
            scale = np.sqrt(np.mean(Xw ** 2, axis=0))
            scale[scale == 0] = 1.0
            Xn = Xw / scale
            yw = y * sw
            lam2 = self.ridge * float(np.sum(Xn ** 2))
            ridge_cols = [m + k for k in range(Kk - 1)] if not template else []
            R = np.zeros((len(ridge_cols), m + Kk))
            for r_i, c in enumerate(ridge_cols):
                R[r_i, c] = math.sqrt(lam2)
            A = np.vstack([Xn, R])
            bb = np.concatenate([yw, np.zeros(len(ridge_cols))])
            lb = np.concatenate([np.full(m, -np.inf), np.zeros(Kk)])
            ub = np.full(m + Kk, np.inf)
            sol = lsq_linear(A, bb, bounds=(lb, ub), method="bvls")
            coef_n = sol.x
            coef = coef_n / scale
            resid = y - X @ coef
            sc = mad_sigma(resid[w > 0])
            result = (coef, coef_n, scale, Xn, R, lam2, ridge_cols, lo, hi, Kk, resid, sc, w.copy())
            if it == TUKEY_ITER or not np.isfinite(sc) or sc <= 0:
                break
            u = resid / (TUKEY_C * sc)
            w = np.where(np.abs(u) < 1, (1 - u * u) ** 2, 0.0)
        coef, coef_n, scale, Xn, R, lam2, ridge_cols, lo, hi, Kk, resid, sc, w = result
        a = coef[m:]
        # covariance on the free parameters (spec 6)
        N = Xn.T @ Xn
        Lam = np.zeros_like(N)
        for c in ridge_cols:
            Lam[c, c] = lam2
        free = np.ones(m + Kk, bool)
        free[m:] = coef_n[m:] > 1e-12 * max(1.0, np.max(np.abs(coef_n)))
        cov_n = np.zeros_like(N)
        dof = 0.0
        sw_ = np.sqrt(w)
        s2 = float(np.sum((resid * sw_) ** 2) / max(1.0, np.sum(w > 0) - free.sum()))
        if free.any():
            try:
                Nf = (N + Lam)[np.ix_(free, free)]
                inv = np.linalg.inv(Nf)
                cov_n[np.ix_(free, free)] = inv * s2
                Hd = np.diag(inv @ N[np.ix_(free, free)])
                fidx = np.nonzero(free)[0]
                dof = float(np.sum(Hd[fidx >= m]))
            except np.linalg.LinAlgError:
                pass
        cov = cov_n / np.outer(scale, scale)
        cov_a = cov[m:, m:]
        r_mid = np.sqrt(lo * hi) if Kk else np.zeros(0)
        p = np.zeros(Kk)
        ps = np.zeros(Kk)
        for j in range(Kk):
            tilt = (r_mid[j] / self.rho0) ** (-self.alpha0)
            p[j] = tilt * np.sum(a[j:])
            ps[j] = tilt * math.sqrt(max(0.0, float(np.sum(cov_a[j:, j:]))))
        residual = np.full(y_all.shape, np.nan)
        residual[ok] = resid
        usable = Kk >= 2 and not np.all(
            (np.sqrt(np.maximum(np.diag(cov_a), 0)) > BASIS_REL_ERR_MAX * np.maximum(a, 1e-300)) | (a <= 0))
        if template:
            usable = Kk == 1
        wf = WingFit(poly=coef[:m], a=a, edges_lo=lo, edges_hi=hi, cov_a=cov_a,
                     r_mid=r_mid, p=p, p_sigma=ps, n_kept=Kk, dof_wing=dof,
                     rms=float(sc), residual=residual, usable=bool(usable))
        if template and Kk:
            wf.template_amp = float(a[0])
        return wf

    def residual_map(self, wf):
        """res_c: block-scale residual, masked blocks filled by normalised
        convolution (sigma = 2 blocks), then a 3x3 block median."""
        g = wf.residual.reshape(self.nby, self.nbx).astype(np.float32)
        filled = normalised_convolution_fill(g, 2.0)
        return ndimage.median_filter(filled, size=3, mode="nearest")

    def p_joint_function(self, wf):
        """p_joint(r) from its samples, interpolated in (ln r, ln p)."""
        good = wf.p > 0
        if good.sum() < 1:
            return None
        lr, lp = np.log(wf.r_mid[good]), np.log(wf.p[good])

        def f(r):
            r = np.asarray(r, float)
            return np.exp(np.interp(np.log(np.maximum(r, 1e-6)), lr, lp))
        return f


# ===========================================================================
# 8. Model rendering (two resolutions) and radial ring measurement
# ===========================================================================

@dataclass
class RenderStar:
    x: float
    y: float
    F: np.ndarray        # (nc,) flux in image units * px (already times s_i)
    R: float             # outer radius, arcsec
    rmin: float = 0.0    # model is zero inside rmin (arcsec)
    taper: bool = False  # smoothstep taper 0.8R -> R (spec 9.3)
    shape: object = None # SPEC (round 20): (ln r [arcsec] grid, (nc, n) factor <= 1) from the star's own ring floor


class GlowModel:
    """A rendered model: a point-sampled coarse grid of all stars plus
    full-resolution inner-zone corrections per star (spec 9.3)."""

    def __init__(self, renderer, coarse, patches, stars, pfun):
        self.r = renderer
        self.coarse = coarse
        self.patches = patches
        self.stars = stars
        self.pfun = pfun

    def native_rows(self, c, y0, y1):
        r = self.r
        out = upsample_coarse(self.coarse[c], r.b, (r.h, r.w), y0, y1)
        for (py0, py1, px0, px1, corr) in self.patches:
            a, b_ = max(py0, y0), min(py1, y1)
            if a >= b_:
                continue
            out[a - y0:b_ - y0, px0:px1] += corr[c][a - py0:b_ - py0]
        return out

    def native(self, c, chunk=512):
        r = self.r
        out = np.empty((r.h, r.w), np.float32)
        for y0 in range(0, r.h, chunk):
            y1 = min(r.h, y0 + chunk)
            out[y0:y1] = self.native_rows(c, y0, y1)
        return out

    def own(self, i, c, X, Y):
        """Exact model of star i at native pixel coordinates."""
        return self.r.star_values(self.stars[i], self.pfun, X, Y, c)

    def own_all(self, i, X, Y):
        """SPEC (round 18): own() for all channels, (nc, ...), with one radius
        evaluation instead of one per channel (same values)."""
        return self.r.star_values(self.stars[i], self.pfun, X, Y)


class ModelRenderer:
    def __init__(self, shape, geom, bprime, nc):
        self.h, self.w = shape
        self.geom = geom
        self.b = int(bprime)
        self.nc = nc
        self.Hc, self.Wc = -(-self.h // self.b), -(-self.w // self.b)
        self.xc = (np.arange(self.Wc) + 0.5) * self.b - 0.5
        self.yc = (np.arange(self.Hc) + 0.5) * self.b - 0.5
        self.r_inner_px = INNER_ZONE_CELLS * self.b

    def star_values(self, st, pfun, X, Y, c=None):
        r = self.geom.r_arcsec(X - st.x, Y - st.y)
        chans = range(self.nc) if c is None else [c]
        sel = (r <= st.R) & (r >= st.rmin)
        out = np.zeros((len(chans),) + np.shape(r), np.float32)
        if not np.any(sel):
            return out if c is None else out[0]
        rr = r[sel]
        wt = np.ones_like(rr)
        if st.taper and st.R > 0:
            wt = 1.0 - smoothstep((rr - 0.8 * st.R) / (0.2 * st.R))
        fac = None
        if st.shape is not None:
            lg, fv = st.shape
            lrr = np.log(np.maximum(rr, 1e-6))
        for k, cc in enumerate(chans):
            if st.F[cc] != 0:
                v = st.F[cc] * self.geom.A_px * pfun(rr, cc) * wt
                if st.shape is not None:
                    v = v * np.interp(lrr, lg, fv[cc], left=fv[cc][0], right=1.0)
                out[k][sel] = v
        return out if c is None else out[0]

    def coarse_window(self, st):
        ex, ey = self.geom.px_extent(st.R)
        i0 = max(0, int(math.floor((st.x - ex + 0.5) / self.b)) - 1)
        i1 = min(self.Wc, int(math.ceil((st.x + ex + 0.5) / self.b)) + 1)
        j0 = max(0, int(math.floor((st.y - ey + 0.5) / self.b)) - 1)
        j1 = min(self.Hc, int(math.ceil((st.y + ey + 0.5) / self.b)) + 1)
        return j0, j1, i0, i1

    def render(self, stars, pfun, ctx=None, inner=True):
        coarse = np.zeros((self.nc, self.Hc, self.Wc), np.float32)
        patches = []
        for n_i, st in enumerate(stars):
            if ctx is not None and n_i % 20 == 0:
                ctx.check_cancel()
            j0, j1, i0, i1 = self.coarse_window(st)
            if j0 < j1 and i0 < i1:
                X, Y = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
                coarse[:, j0:j1, i0:i1] += self.star_values(st, pfun, X, Y)
            if not inner:
                continue
            R_in = self.r_inner_px
            # SPEC (round 18): the patch is cut to the star's own extent. Beyond
            # R the exact model is 0, and so is the bilinear upsample of the
            # star's coarse samples once all four cells feeding a pixel (each
            # within b' px of it) lie beyond R: the correction is exactly 0 more
            # than R + b' px from the star. Most casters have R of 10-26 px and
            # were given 129 x 129 patches of zeros; the values inside the cut
            # patch are unchanged (the feather still runs over R_in).
            ex, ey = self.geom.px_extent(st.R)
            hx, hy = min(R_in, ex + 2 * self.b + 2), min(R_in, ey + 2 * self.b + 2)
            x0 = max(0, int(math.floor(st.x - R_in)), int(math.floor(st.x - hx)))
            x1 = min(self.w, int(math.ceil(st.x + R_in)) + 1, int(math.ceil(st.x + hx)) + 1)
            y0 = max(0, int(math.floor(st.y - R_in)), int(math.floor(st.y - hy)))
            y1 = min(self.h, int(math.ceil(st.y + R_in)) + 1, int(math.ceil(st.y + hy)) + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
            exact = self.star_values(st, pfun, X, Y)
            # this star's own coarse samples on the cells feeding the cutout
            cj0 = max(0, y0 // self.b - 1)
            cj1 = min(self.Hc, (y1 - 1) // self.b + 2)
            ci0 = max(0, x0 // self.b - 1)
            ci1 = min(self.Wc, (x1 - 1) // self.b + 2)
            CX, CY = np.meshgrid(self.xc[ci0:ci1], self.yc[cj0:cj1])
            own_c = self.star_values(st, pfun, CX, CY)
            corr = np.empty_like(exact)
            for c in range(self.nc):
                up = upsample_coarse(own_c[c], self.b, (self.h, self.w), y0, y1, x0, x1,
                                     grid_origin=(cj0, ci0))
                corr[c] = exact[c] - up
            # SPEC (round 4): the exact inner patch is feathered out over the
            # outer quarter of the inner zone instead of ending at a hard
            # circle, where the step to the bilinear coarse model drew a ring.
            inside = (1.0 - smoothstep((np.hypot(X - st.x, Y - st.y) - 0.75 * R_in) / (0.25 * R_in))).astype(np.float32)
            corr *= inside[None]
            patches.append((y0, y1, x0, x1, corr))
        return GlowModel(self, coarse, patches, stars, pfun)


class RingGeometry:
    """Shared ring edges (arcsec) and the native/coarse split (spec 8.2)."""

    def __init__(self, geom, fwhm_arcsec, maxradius):
        sc = geom.scale
        step = max(sc, 0.25 * fwhm_arcsec)
        lin_end = 4.0 * fwhm_arcsec
        lin = np.arange(0.0, lin_end + 1e-9, step)
        if lin[-1] < lin_end - 1e-9:
            lin = np.append(lin, lin_end)
        lo = lin[-1]
        n_log = max(1, int(math.ceil(math.log(maxradius / lo) / RING_DLNR)))
        logs = lo * np.exp(RING_DLNR * np.arange(1, n_log + 1))
        logs[-1] = max(logs[-1], maxradius)
        self.edges = np.concatenate([lin, logs])
        self.lo, self.hi = self.edges[:-1], self.edges[1:]
        nlin = lin.size - 1
        self.mid = np.where(np.arange(self.lo.size) < nlin, 0.5 * (self.lo + self.hi),
                            np.sqrt(np.maximum(self.lo, 1e-9) * self.hi))
        self.native = self.hi / sc <= RING_NATIVE_PX
        self.n = self.lo.size
        # SPEC: rings inside 1 FWHM hold fewer than 20 pixels per star by
        # geometry; p(0) (spec 8.1) needs them, so they only need 3 pixels.
        self.min_n = np.where(self.hi <= fwhm_arcsec + 1e-9, 3, RING_MIN_N)
        self.fwhm = fwhm_arcsec
        # SPEC (round 3): rings beyond 4 FWHM take the lower quartile of 8 sector
        # medians instead of the full-ring median. Glow is azimuthally symmetric,
        # so its sectors agree; nebulosity, galaxies or a neighbour's halo lift
        # only some sectors and are ignored; the estimate errs low, as required
        # by the no-undershoot rule.
        self.sectored = self.mid >= SECTOR_MIN_FWHM * fwhm_arcsec
        # SPEC (round 4): the sector value is blended in over 3-5 FWHM: the
        # lower quartile of the sector medians lies below the ring median, and
        # the hard switch at 4 FWHM put a step of up to ~20% into the profile
        # (M31 full frame), drawn as a circle at 4 FWHM around every star.
        self.sector_w = smoothstep((self.mid - (SECTOR_MIN_FWHM - 1) * fwhm_arcsec) / (2 * fwhm_arcsec))
        # SPEC (round 19): the azimuthal floor (see FLOOR_QUANTILE) is blended in over
        # FLOOR_START_FWHM, from the edge of the core (2 FWHM) on, not with the sector
        # value over 3-5 FWHM: the lanes start at the core, and with the sector blend
        # the model at 8-13 px around the M31 G = 4.5 star stayed 5-10% above the
        # floor (a dark ring of pixels at 12.9 px, where the blend ends)
        self.floor_w = smoothstep((self.mid - FLOOR_START_FWHM[0] * fwhm_arcsec)
                                  / ((FLOOR_START_FWHM[1] - FLOOR_START_FWHM[0]) * fwhm_arcsec))
        # SPEC (round 3): beyond 4 FWHM a ring tolerates RING_MAX_SAT_FRAC_FAR of
        # saturated pixels instead of 0.5%: a very bright star's own saturated
        # diffraction spikes cross its rings far out, the saturated pixels never
        # enter the value (masked; sector lower quartile), and the rule had
        # removed exactly the rings that measure the far wing.
        self.max_sat = np.where(self.sectored, RING_MAX_SAT_FRAC_FAR, RING_MAX_SAT_FRAC)
        self.scale = sc


@dataclass
class StarRings:
    med: np.ndarray        # (nc, n) ring medians, image units
    sig: np.ndarray        # (nc, n) sigma_stat
    n: np.ndarray          # (n,) valid pixel (cell) count
    ok: np.ndarray         # (n,) ring passes the exclusion rules
    others: np.ndarray     # (n,) ring median of the other stars' model (channel mean)
    r_out: float
    med_c: object = None   # (nc, n) SPEC (round 12): central (azimuthal median) ring values
    flo: object = None     # (nc, n) SPEC (round 20): noise-corrected azimuthal floor (NaN where none)


class RingMeasurer:
    """Two-resolution ring medians with cached labels (spec 8.2)."""

    def __init__(self, shape, geom, rings, nc, bprime, eta, report):
        self.h, self.w = shape
        self.geom = geom
        self.rg = rings
        self.nc = nc
        self.b = bprime
        self.eta = eta
        self.report = report
        self.cache = {}

    def _labels(self, key, xs, ys, cx, cy, r_out, valid, sat, native, nat, cache=True):
        ck = (key, native, round(r_out, 3), nat.tobytes())
        if cache and ck in self.cache:
            return self.cache[ck]
        r = self.geom.r_arcsec(xs - cx, ys - cy)
        lab = np.searchsorted(self.rg.edges, r, side="right") - 1
        inring = (lab >= 0) & (lab < self.rg.n) & (r <= r_out)
        if native:
            inring &= nat[np.clip(lab, 0, self.rg.n - 1)]
        else:
            inring &= ~nat[np.clip(lab, 0, self.rg.n - 1)]
        lab_all = np.where(inring, lab, -1)
        n_geom = np.bincount(lab_all[inring], minlength=self.rg.n)
        # sat is the saturated fraction of each pixel / cell (0..1)
        n_sat = np.bincount(lab_all[inring], weights=np.asarray(sat, float)[inring], minlength=self.rg.n)
        use = inring & valid
        lv = lab_all[use]
        order = np.argsort(lv, kind="stable")
        lv_sorted = lv[order]
        bounds = np.searchsorted(lv_sorted, np.arange(self.rg.n + 1))
        res = (use, order, bounds, n_geom, n_sat)
        if cache:
            self.cache[ck] = res
        return res

    def _medians(self, vals_sorted, bounds, rings_idx, sec_sorted=None, with_mad=True):
        """Per ring: the full-ring median and MAD and, where sectors are
        asked for (SPEC round 12), the SECTOR_QUANTILE percentile and the
        median of the sector medians and their robust scatter (NaN where
        fewer than SECTOR_MIN_VALID sectors are populated). The blend of the
        full-ring and sector values is made by the caller."""
        n = self.rg.n
        med = np.full(n, np.nan)
        mad = np.full(n, np.nan)
        lq = np.full(n, np.nan)
        msec = np.full(n, np.nan)
        ssec = np.full(n, np.nan)
        # SPEC (round 19): azimuthal floor per ring (FLOOR_QUANTILE percentile of the
        # bin medians, no noise correction yet), its number of bins and the noise of
        # one bin median (see _ring_floor, measure)
        flo = np.full(n, np.nan)
        fnb = np.zeros(n)
        fsb = np.full(n, np.nan)
        # SPEC (round 18): one sort per array for all rings and sectors instead
        # of one np.median per ring and sector (same values, see grouped_median)
        cnt = np.diff(bounds)
        want = np.zeros(n, bool)
        want[np.asarray(list(rings_idx), np.int64)] = True
        want &= cnt >= 1
        if not want.any():
            return med, mad, lq, msec, ssec, (flo, fnb, fsb)
        lab = np.repeat(np.arange(n), cnt)
        keep = want[lab]
        v = vals_sorted[:lab.size][keep]
        lab = lab[keep]
        cw = np.where(want, cnt, 0)
        starts = np.concatenate([[0], np.cumsum(cw)[:-1]])
        o1 = group_order(v, lab, n)
        m = grouped_median(v[o1], starts, cw)
        med[want] = m[want]
        if not with_mad and sec_sorted is None:
            return med, mad, lq, msec, ssec, (flo, fnb, fsb)
        dev = np.abs(v - m[lab])
        mad[want] = grouped_median(dev[group_order(dev, lab, n)], starts, cw)[want]
        if sec_sorted is None:
            return med, mad, lq, msec, ssec, (flo, fnb, fsb)
        sw = want & ((self.rg.sector_w > 0) | (self.rg.floor_w > 0))
        if not sw.any():
            return med, mad, lq, msec, ssec, (flo, fnb, fsb)
        fb = sec_sorted[:keep.size][keep]
        # SPEC (round 19): sec_sorted holds the fine azimuthal bin (0..FLOOR_BINS-1)
        # plus FLOOR_BINS times the checkerboard parity of the pixel (see _sectors);
        # the sector is 1/N_SECTORS of the bin
        par = fb // FLOOR_BINS
        fb = fb % FLOOR_BINS
        s = fb // (FLOOR_BINS // N_SECTORS)
        # the (ring, sector) groups from the value-sorted rings by one stable
        # integer sort: the values stay sorted (NaN last) within each sector
        ks = sw[lab[o1]]
        vk = v[o1][ks]
        lk = lab[o1][ks]
        self._ring_floor(vk, lk, fb[o1][ks], par[o1][ks], cnt, sw, flo, fnb, fsb)
        g = lab[o1][ks] * N_SECTORS + s[o1][ks]
        o2 = np.argsort(g.astype(np.uint16) if n * N_SECTORS <= 65536 else g, kind="stable")
        scnt = np.bincount(g, minlength=n * N_SECTORS)
        smed = grouped_median(vk[o2], np.concatenate([[0], np.cumsum(scnt)[:-1]]), scnt)
        smed = smed.reshape(n, N_SECTORS)[sw]
        rows_k = np.nonzero(sw)[0]
        for rows, A in rowwise_stats(smed, scnt.reshape(n, N_SECTORS)[sw] >= 3, SECTOR_MIN_VALID):
            k = rows_k[rows]
            lq[k] = np.percentile(A, SECTOR_QUANTILE, axis=1)
            mm = np.median(A, axis=1)
            msec[k] = mm
            ssec[k] = 1.4826 * np.median(np.abs(A - mm[:, None]), axis=1).astype(np.float64)
        return med, mad, lq, msec, ssec, (flo, fnb, fsb)

    @staticmethod
    def _ring_floor(vk, lk, fk, pk, cnt, sw, flo, fnb, fsb):
        """SPEC (round 19): the azimuthal floor of the rings sw. vk: values sorted
        by (ring, value), lk their rings, fk their fine bins (0..FLOOR_BINS-1), pk
        their checkerboard parity, cnt the samples per ring. Each ring uses the
        finest bin count of FLOOR_BIN_COUNTS that leaves FLOOR_MIN_N samples per
        bin; bins holding fewer than 3 samples, or none in one checkerboard half
        (masked neighbours, frame edge), are not used. A bin's value is the mean
        of the medians of its two checkerboard halves. Fills, in place, flo
        (FLOOR_QUANTILE percentile of the bin values), fnb (bins used) and fsb
        (noise of one bin value). fsb is measured, not modelled: the two halves
        see the same radius and azimuth, so lanes and the radial gradient cancel
        in the difference d of their medians, and sd(value) = sd(d) / 2.
        Neighbouring pixels of a registered stack are positively correlated,
        which makes d, and so the noise correction, smaller: it errs low."""
        n = cnt.size
        nbk = np.zeros(n, np.int64)
        for nb in FLOOR_BIN_COUNTS:
            nbk = np.where(cnt >= nb * FLOOR_MIN_N, nb, nbk)
        use_r = sw & (nbk > 0)
        if not use_r.any():
            return
        m = np.where(nbk > 0, FLOOR_BINS // np.maximum(nbk, 1), 0)
        ks = use_r[lk]
        if not ks.any():
            return
        lr, v = lk[ks], vk[ks]
        mk = m[lr]
        # the two checkerboard halves of every bin, by one stable integer sort (the
        # values stay sorted within each half)
        g2 = (lr * FLOOR_BINS + (fk[ks] // mk) * mk) * 2 + pk[ks]
        ng = n * FLOOR_BINS
        o = np.argsort(g2.astype(np.uint16) if 2 * ng <= 65536 else g2, kind="stable")
        hc = np.bincount(g2, minlength=2 * ng)
        hm = grouped_median(v[o], np.concatenate([[0], np.cumsum(hc)[:-1]]), hc).reshape(n, FLOOR_BINS, 2)
        hc = hc.reshape(n, FLOOR_BINS, 2)
        rows_k = np.nonzero(use_r)[0]
        hm, hc = hm[rows_k], hc[rows_k]
        # a bin's value is the mean of its two half medians: its noise is that of
        # the full-bin median, and sd(value) = sd(d) / 2 exactly for d = h0 - h1
        okb = (hc.sum(axis=2) >= 3) & np.all(hc >= 1, axis=2)
        nv = okb.sum(axis=1)
        dd = np.where(okb, np.abs(hm[:, :, 0].astype(np.float64) - hm[:, :, 1]), np.inf)
        dd.sort(axis=1)
        sb = 1.4826 * sorted_row_percentile(dd, nv, 50.0) / 2.0
        A = np.where(okb, 0.5 * (hm[:, :, 0].astype(np.float64) + hm[:, :, 1]), np.inf)
        A.sort(axis=1)
        q = sorted_row_percentile(A, nv, FLOOR_QUANTILE)
        good = nv >= FLOOR_MIN_BINS
        k = rows_k[good]
        flo[k] = q[good]
        fnb[k] = nv[good]
        fsb[k] = sb[good]

    @staticmethod
    def floor_noise(nb):
        """SPEC (round 19): mean and standard deviation of the FLOOR_QUANTILE
        percentile (numpy's linear interpolation) of nb standard normal values:
        Blom's approximation of the expected order statistics, and the
        first-order variance p(1 - p) / ((nb + 2) phi(z_p)^2) at the
        interpolated rank (about 13% low for the minimum of 120)."""
        nb = np.maximum(np.asarray(nb, float), 2.0)
        h = FLOOR_QUANTILE / 100.0 * (nb - 1)
        k = np.floor(h)
        e0 = ndtri((k + 1 - 0.375) / (nb + 0.25))
        e1 = ndtri((np.minimum(k + 1, nb - 1) + 1 - 0.375) / (nb + 0.25))
        pr = (h + 1) / (nb + 1)
        zp = ndtri(pr)
        sd = np.sqrt(pr * (1 - pr) / (nb + 2)) * math.sqrt(2 * math.pi) * np.exp(0.5 * zp * zp)
        return e0 + (h - k) * (e1 - e0), sd

    @staticmethod
    def _sectors(X, Y, x, y, step=1.0):
        """SPEC (round 19): the fine azimuthal bin (0..FLOOR_BINS-1) plus FLOOR_BINS
        times the checkerboard parity of the pixel (or cell, step = b'); the
        45-degree sector is bin // (FLOOR_BINS // N_SECTORS)."""
        a = (np.arctan2(Y - y, X - x) + np.pi) / (2 * np.pi) * FLOOR_BINS
        par = (np.floor(X / step).astype(np.int64) + np.floor(Y / step).astype(np.int64)) & 1
        return np.clip(a.astype(np.int64), 0, FLOOR_BINS - 1) + FLOOR_BINS * par

    def measure(self, key, x, y, r_out, work_native, work_coarse, own_native, own_coarse,
                others_native, others_coarse, valid_native, sat_native, valid_coarse, sat_coarse,
                native_limit_px=RING_NATIVE_PX, force=None, gate=None):
        """work_*: lists per channel of (img - bg - total model); own_* add the
        star's own model back; others_* is the channel-mean model of the
        other stars. Returns StarRings."""
        rg = self.rg
        nc = self.nc
        if force == "native":
            nat = np.ones(rg.n, bool)
        elif force == "coarse":
            nat = np.zeros(rg.n, bool)
        else:
            nat = rg.native
        med = np.full((nc, rg.n), np.nan)
        sig = np.full((nc, rg.n), np.nan)
        # SPEC (round 12): the sector statistics are kept apart from the
        # full-ring median until the noise error is known (see the end)
        lq = np.full((nc, rg.n), np.nan)
        msec = np.full((nc, rg.n), np.nan)
        ssec = np.full((nc, rg.n), np.nan)
        # SPEC (round 19): azimuthal floor, bins used and noise of one bin
        flo = np.full((nc, rg.n), np.nan)
        fnb = np.zeros((nc, rg.n))
        fsb = np.full((nc, rg.n), np.nan)
        nn = np.zeros(rg.n)
        own_ring = np.zeros(rg.n)      # SPEC (round 19): the star's own model per ring (channel mean)
        oth = np.full(rg.n, np.nan)
        ok = np.zeros(rg.n, bool)
        area = math.pi * (rg.hi ** 2 - rg.lo ** 2) / self.geom.A_px
        # --- native part
        rpx = (min(r_out / rg.scale, native_limit_px) if force != "coarse" else 0) + 1
        x0, x1 = max(0, int(x - rpx)), min(self.w, int(x + rpx) + 2)
        y0, y1 = max(0, int(y - rpx)), min(self.h, int(y + rpx) + 2)
        if x0 < x1 and y0 < y1:
            X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
            # SPEC: saturated pixels inside the (already masked) neighbour cores
            # do not count towards the 0.5% saturation rule, which is meant for
            # the star's own saturation, bleeding and blooming.
            v_ok, nb_mask = valid_native(y0, y1, x0, x1, x, y)
            s_ok = sat_native[y0:y1, x0:x1] & ~nb_mask
            use, order, bounds, ng, ns = self._labels(key, X, Y, x, y, r_out, v_ok, s_ok, True, nat)
            idx = [k for k in range(rg.n) if nat[k] and bounds[k + 1] > bounds[k]]
            ownv = own_native(X[use], Y[use])
            secs = self._sectors(X[use], Y[use], x, y)[order]
            cnt_n = np.diff(bounds)
            gv = ownv if gate is None else gate(X[use], Y[use])
            own_ring += np.bincount(np.repeat(np.arange(rg.n), cnt_n), minlength=rg.n,
                                    weights=np.mean(gv, axis=0)[order].astype(np.float64)) / np.maximum(cnt_n, 1)
            for c in range(nc):
                vals = (work_native[c][y0:y1, x0:x1][use] + ownv[c])[order]
                m, d, q, ms, ss, fl = self._medians(vals, bounds, idx, secs)
                med[c, idx] = m[idx]
                sig[c, idx] = d[idx]
                lq[c, idx], msec[c, idx], ssec[c, idx] = q[idx], ms[idx], ss[idx]
                flo[c, idx], fnb[c, idx], fsb[c, idx] = fl[0][idx], fl[1][idx], fl[2][idx]
            if others_native is not None:
                ov = (others_native[y0:y1, x0:x1][use] - np.mean(ownv, axis=0))[order]
                m = self._medians(ov, bounds, idx, with_mad=False)[0]
                oth[idx] = m[idx]
            cnt = np.diff(bounds)
            for k in range(rg.n):
                if nat[k] and ng[k] > 0:
                    nn[k] = cnt[k]
                    ok[k] = (ns[k] <= rg.max_sat[k] * ng[k]) and cnt[k] >= rg.min_n[k] \
                        and cnt[k] >= RING_MIN_COVERAGE * area[k]
        # --- coarse part
        if (force == "coarse" or (force is None and r_out / rg.scale > native_limit_px)) \
                and work_coarse is not None:
            b = self.b
            Hc, Wc = work_coarse[0].shape
            ex, ey = self.geom.px_extent(r_out)
            i0 = max(0, int((x - ex) // b) - 1)
            i1 = min(Wc, int((x + ex) // b) + 2)
            j0 = max(0, int((y - ey) // b) - 1)
            j1 = min(Hc, int((y + ey) // b) + 2)
            if i0 < i1 and j0 < j1:
                XC, YC = np.meshgrid((np.arange(i0, i1) + 0.5) * b - 0.5, (np.arange(j0, j1) + 0.5) * b - 0.5)
                v_ok = valid_coarse[j0:j1, i0:i1]
                s_ok = sat_coarse[j0:j1, i0:i1]
                use, order, bounds, ng, ns = self._labels(key, XC, YC, x, y, r_out, v_ok, s_ok, False, nat)
                idx = [k for k in range(rg.n) if (not nat[k]) and bounds[k + 1] > bounds[k]]
                ownv = own_coarse(XC[use], YC[use])
                secs = self._sectors(XC[use] + 0.5, YC[use] + 0.5, x + 0.5, y + 0.5, b)[order]
                cnt_c = np.diff(bounds)
                gv = ownv if gate is None else gate(XC[use], YC[use])
                own_ring += np.bincount(np.repeat(np.arange(rg.n), cnt_c), minlength=rg.n,
                                        weights=np.mean(gv, axis=0)[order].astype(np.float64)) / np.maximum(cnt_c, 1)
                for c in range(nc):
                    vals = (work_coarse[c][j0:j1, i0:i1][use] + ownv[c])[order]
                    m, d, q, ms, ss, fl = self._medians(vals, bounds, idx, secs)
                    med[c, idx] = m[idx]
                    sig[c, idx] = d[idx]
                    lq[c, idx], msec[c, idx], ssec[c, idx] = q[idx], ms[idx], ss[idx]
                    flo[c, idx], fnb[c, idx], fsb[c, idx] = fl[0][idx], fl[1][idx], fl[2][idx]
                if others_coarse is not None:
                    ov = (others_coarse[j0:j1, i0:i1][use] - np.mean(ownv, axis=0))[order]
                    m = self._medians(ov, bounds, idx, with_mad=False)[0]
                    oth[idx] = m[idx]
                cnt = np.diff(bounds)
                for k in range(rg.n):
                    if (not nat[k]) and ng[k] > 0:
                        nn[k] = cnt[k]
                        ok[k] = (ns[k] <= rg.max_sat[k] * ng[k]) and cnt[k] >= RING_MIN_N \
                            and cnt[k] >= RING_MIN_COVERAGE * area[k] / (b * b)
        # SPEC (round 19): the floor of the block-median rings beyond 50 px is taken
        # from the native pixels where the star's ring is bright enough for its lanes
        # to matter (FLOOR_GLOW_SIGMA): a 4 x 4 cell is as wide as a lane there,
        # and bins of enough cells would span 10-30 degrees. Only the floor is
        # measured natively; the ring medians and errors stay the block-median ones.
        sbg0 = getattr(self, "sig_bg", None)
        if force is None and sbg0 is not None and work_native is not None and np.any(~nat):
            # the rings, contiguous from the native limit outwards, where the star's
            # own model is at least FLOOR_GLOW_SIGMA[0] sigma_bg
            kf = (~nat) & (rg.floor_w > 0) & (rg.hi <= r_out) & (rg.hi / rg.scale <= FLOOR_NATIVE_MAX_PX) \
                & (own_ring >= FLOOR_GLOW_SIGMA[0] * float(np.mean(sbg0)))
            k0 = int(np.argmax(~nat)) if np.any(~nat) else rg.n
            run = np.cumprod(kf[k0:]).astype(bool)
            kf = np.zeros(rg.n, bool)
            kf[k0:] = run
            if kf.any():
                r_f = float(rg.hi[kf].max())
                rpx = r_f / rg.scale + 1
                x0, x1 = max(0, int(x - rpx)), min(self.w, int(x + rpx) + 2)
                y0, y1 = max(0, int(y - rpx)), min(self.h, int(y + rpx) + 2)
                if x0 < x1 and y0 < y1:
                    X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
                    v_ok, nb_mask = valid_native(y0, y1, x0, x1, x, y)
                    s_ok = sat_native[y0:y1, x0:x1] & ~nb_mask
                    use, order, bounds, _, _ = self._labels(("floor", key), X, Y, x, y, r_f, v_ok, s_ok,
                                                            True, kf, cache=False)
                    ownv = own_native(X[use], Y[use])
                    fbin = self._sectors(X[use], Y[use], x, y)[order]
                    cntf = np.diff(bounds)
                    labf = np.repeat(np.arange(rg.n), cntf)
                    for c in range(nc):
                        vals = (work_native[c][y0:y1, x0:x1][use] + ownv[c])[order]
                        o1 = group_order(vals, labf, rg.n)
                        f0, f1, f2 = np.full(rg.n, np.nan), np.zeros(rg.n), np.full(rg.n, np.nan)
                        self._ring_floor(vals[o1], labf[o1], fbin[o1] % FLOOR_BINS, fbin[o1] // FLOOR_BINS,
                                         cntf, kf, f0, f1, f2)
                        got = kf & np.isfinite(f0)
                        flo[c, got], fnb[c, got], fsb[c, got] = f0[got], f1[got], f2[got]
                    del X, Y, use, order, ownv, fbin, labf
        with np.errstate(all="ignore"):
            sig = MEDIAN_EFF * 1.4826 * sig / np.sqrt(np.maximum(nn, 1) / self.eta)[None, :]
            # SPEC (round 7): floor of the ring error at the background-noise
            # limit: the median of n pixels (n b'^2 for block-median rings) whose
            # noise is at least sigma_bg, with the stack's noise correlation eta,
            # cannot be known better than 1.2533 sigma_bg sqrt(eta / n). A ring of
            # identical values (a constant fill, a flat clipped region) has
            # MAD = 0 and would otherwise get an unbounded weight.
            sbg = getattr(self, "sig_bg", None)
            if sbg is not None:
                npx = np.where(nat, np.maximum(nn, 1), np.maximum(nn, 1) * float(self.b) ** 2)
                floor = MEDIAN_EFF * np.asarray(sbg, float)[:, None] * np.sqrt(self.eta / npx)[None, :]
                sig = np.where(np.isfinite(sig), np.maximum(sig, floor), sig)
            # SPEC (round 12): sector-based ring values, blended in over 3-5 FWHM
            # (sector_w). Two values are kept: med, the conservative value that
            # renders the model (see PROFILE_SAFETY), and med_c, the azimuthal
            # median of the sector medians, which carries the shape (hand-over
            # slope, tail alpha) without the asymmetry-dependent deficit of the
            # conservative value. The error describes the estimator actually
            # used: the sector value is SECTOR_NOISE_FACTOR noisier than the
            # full-ring median (simulation: 1.2 for the lower quartile and the
            # median of 8 sectors), plus the real sector-to-sector scatter over
            # sqrt(N_SECTORS). The variance of a sector median is N_SECTORS times
            # the full-ring noise variance plus the azimuthal asymmetry, so the
            # asymmetry is ssec^2 - N_SECTORS sig^2 (floored at 0): rings whose
            # sectors agree within the noise get no extra error, and no
            # lower-bound shift.
            have = np.isfinite(msec) & np.isfinite(sig)
            w = np.where(have, rg.sector_w[None, :], 0.0)
            s_asym2 = np.maximum(np.nan_to_num(ssec) ** 2 - N_SECTORS * np.nan_to_num(sig) ** 2, 0.0)
            med_c = np.where(have, (1 - w) * med + w * np.nan_to_num(msec), med)
            if PROFILE_SAFETY == "lowerbound":
                cons = np.nan_to_num(msec) - PROFILE_LB_Z * np.sqrt(s_asym2)
            else:
                cons = np.nan_to_num(lq)
            # SPEC (round 19): the conservative value is also bounded by the azimuthal
            # floor (see FLOOR_QUANTILE), so that bright lanes cannot size the model.
            # The floor's noise bias (the expected percentile of fnb noisy bin
            # values, floor_noise) is removed with the measured noise of one bin
            # (fsb, see _ring_floor); without it a noise-limited ring would lose
            # ~2.5 sqrt(fnb) times its own error. The floor is noisier than the
            # median (sd fsb, a factor sd sqrt(fnb) ~ 4.5 on the full-ring error for
            # the minimum of 120 bins), so it replaces the conservative value only
            # as far as the deficit D = cons - floor is significant: not at all
            # below FLOOR_SIG[0] sd, fully beyond FLOOR_SIG[1] sd (smoothstep), with
            # the error blended alike. Lanes tens of sigma deep (the M31 and bubble
            # bright stars) get the floor; a noise-limited ring, whose sectors and
            # bins agree within the noise, keeps the sector value and its error,
            # so the reach walk and the far rings are not drowned in floor noise.
            sig0 = sig
            med = np.where(have, (1 - w) * med + w * cons, med)
            sig = np.sqrt(((1 + (SECTOR_NOISE_FACTOR - 1) * w) * sig) ** 2 + w * s_asym2 / N_SECTORS)
            fe, fsd = self.floor_noise(np.maximum(fnb, 2))
            fsd_v = fsd * np.nan_to_num(fsb)
            fl_v = flo - fe * np.nan_to_num(fsb)
            use_f = np.isfinite(fl_v) & np.isfinite(med) & (fnb >= FLOOR_MIN_BINS) & (fl_v < med) \
                & (rg.floor_w > 0)[None, :]
            with np.errstate(divide="ignore", invalid="ignore"):
                zf = np.where(use_f, (med - fl_v) / np.maximum(fsd_v, 1e-300), 0.0)
            wf = np.where(use_f, smoothstep((zf - FLOOR_SIG[0]) / (FLOOR_SIG[1] - FLOOR_SIG[0])), 0.0)
            # ... and only where the star's own glow is bright against the sky
            # (FLOOR_GLOW_SIGMA): fainter, a lane is a fraction of a sigma deep,
            # while the minimum over the azimuth is set by the sky's own structure
            # and the background model's errors (dark gaps between nebula
            # filaments on bubble-rgb drove it negative beyond 3', and the far wing
            # was lost with the reach)
            if sbg is not None:
                gl = own_ring / max(float(np.mean(sbg)), 1e-30)
                wf = wf * smoothstep((gl - FLOOR_GLOW_SIGMA[0]) / (FLOOR_GLOW_SIGMA[1] - FLOOR_GLOW_SIGMA[0]))[None, :]
            else:
                wf = np.zeros_like(wf)
            wf = wf * rg.floor_w[None, :]
            med = np.where(use_f, med - wf * (med - np.nan_to_num(fl_v)), med)
            nf = 1.0 + wf * np.maximum(fsd * np.sqrt(np.maximum(fnb, 1)) - 1.0, 0.0)
            sig = np.where(use_f, np.maximum(sig, nf * sig0), sig)
        ok &= np.all(np.isfinite(med), axis=0)
        return StarRings(med=med, sig=sig, n=nn, ok=ok, others=oth, r_out=r_out, med_c=med_c,
                         flo=np.where((fnb >= FLOOR_MIN_BINS) & np.isfinite(fl_v), fl_v, np.nan))


# ===========================================================================
# 9. Extended PSF (spec 8.3, 8.4)
# ===========================================================================

class RadialPSF:
    """p_c(r) in arcsec^-2 per calibrated flux, sampled at radii r (arcsec),
    per channel plus luminance. Evaluated by linear interpolation in
    (ln r, ln p), with r clamped to the first sample (spec 9.3)."""

    def __init__(self, r, p, p_lum, sig=None, sig_lum=None, p0=None, meta=None):
        self.r = np.asarray(r, float)
        self.p = np.atleast_2d(np.asarray(p, float))
        self.p_lum = np.asarray(p_lum, float)
        self.sig = np.zeros_like(self.p) if sig is None else np.atleast_2d(np.asarray(sig, float))
        self.sig_lum = np.zeros_like(self.p_lum) if sig_lum is None else np.asarray(sig_lum, float)
        self.nc = self.p.shape[0]
        self.meta = meta or {}
        self._prep()
        self.p0 = (np.array([self.eval(np.array([0.0]), c)[0] for c in range(self.nc)])
                   if p0 is None else np.asarray(p0, float))

    def _prep(self):
        self.lr = np.log(np.maximum(self.r, 1e-6))
        self.tabs = []
        # SPEC (round 7): non-positive samples inside the core (r <= core_r,
        # 2 FWHM) are dropped and interpolated over; the profile ends at the
        # first non-positive value beyond the core (spec 8.3). One bad core
        # ring had ended whole channels at 1.5" (bubble-rgb: no R/B model).
        core_r = float(self.meta.get("core_r", 0.0) or 0.0)
        for prof in list(self.p) + [self.p_lum]:
            pos = np.isfinite(prof) & (prof > 0)
            beyond = (~pos) & (self.r > core_r)
            end = int(np.argmax(beyond)) if beyond.any() else prof.size
            keep = pos.copy()
            keep[end:] = False
            if not keep.any():
                keep[0] = True
            lr_k = self.lr[keep]
            lp = np.log(np.maximum(prof[keep], 1e-300))
            self.tabs.append((lr_k, lp, self.r[keep][-1]))

    def eval(self, r, c):
        """c = channel index, or -1 / nc for luminance."""
        lr, lp, rend = self.tabs[c if 0 <= c < self.nc else self.nc]
        r = np.asarray(r, float)
        x = np.log(np.maximum(r, self.r[0]))
        out = np.exp(np.interp(x, lr, lp))
        return np.where(r <= rend, out, 0.0)

    def pfun(self):
        return lambda r, c: self.eval(r, c)

    def r_end(self, c=-1):
        return self.tabs[c if 0 <= c < self.nc else self.nc][2]


def generic_wing_arcsec(r, fwhm_arcsec):
    """p_gen(r) = 1e-4 (r / 4 FWHM)^-2.5 per FWHM^2 (spec 9.1), r >= 3 FWHM."""
    r = np.asarray(r, float)
    return np.where(r >= 3 * fwhm_arcsec,
                    GEN_WING_AMP * (np.maximum(r, 1e-6) / (4 * fwhm_arcsec)) ** -2.5 / fwhm_arcsec ** 2, 0.0)


def make_p0_function(pjoint, rho0, fwhm_arcsec):
    """p^(0): p_joint,L beyond rho0, the generic wing rescaled to be
    continuous at rho0 inside it, zero inside 3 FWHM (spec 6)."""
    if pjoint is None:
        return lambda r, c=0: generic_wing_arcsec(r, fwhm_arcsec)
    g0 = generic_wing_arcsec(np.array([rho0]), fwhm_arcsec)[0]
    pj0 = float(pjoint(np.array([rho0]))[0])
    k = pj0 / g0 if g0 > 0 else 1.0

    def f(r, c=0):
        r = np.asarray(r, float)
        return np.where(r >= rho0, pjoint(np.maximum(r, rho0)), k * generic_wing_arcsec(r, fwhm_arcsec))
    return f


class ExtendedPSFBuilder:
    """Combination of the per-star rings, reach, extension beyond r_meas,
    chromaticity and monotonicity (spec 8.3)."""

    def __init__(self, rings_geom, A_px, fwhm_arcsec, maxradius, nc, report):
        self.rg = rings_geom
        self.A = A_px
        self.fwhm = fwhm_arcsec
        self.maxradius = maxradius
        self.nc = nc
        self.report = report

    def per_star(self, rings, Fpred, sig_agree, sig_sys, c):
        """p_i and sigma_tot for one channel (c < nc) or luminance (c = -1).
        SPEC (round 12): also returns the central (azimuthal median) p_i,
        with the same validity and errors, for the shape fits."""
        n_st = len(rings)
        P = np.full((n_st, self.rg.n), np.nan)
        Pc = np.full((n_st, self.rg.n), np.nan)
        S = np.full((n_st, self.rg.n), np.nan)
        SA = np.zeros(n_st)
        for i, sr in enumerate(rings):
            med_c = sr.med if sr.med_c is None else sr.med_c
            if c >= 0:
                F = Fpred[i, c]
                med, sg = sr.med[c], sr.sig[c]
                mc = med_c[c]
                sa, ss = sig_agree[c], sig_sys[c]
                ss2 = ss ** 2
            else:
                F = np.sum(Fpred[i])
                med = np.sum(sr.med, axis=0)
                mc = np.sum(med_c, axis=0)
                sg = np.sqrt(np.sum(sr.sig ** 2, axis=0))
                sa = float(np.mean(sig_agree))
                ss2 = float(np.sum(np.asarray(sig_sys) ** 2))
            if not (F > 0):
                continue
            p = med / (F * self.A)
            st2 = (sg / (F * self.A)) ** 2 + ss2 / (F * self.A) ** 2
            ok = sr.ok & np.isfinite(p) & np.isfinite(st2) & (st2 > 0)
            # SPEC (round 3): similar to the flux refinement (9.2), rings dominated
            # by the other stars' model (> 3x the star's own ring) are not used:
            # a faint star inside a bright star's glow measures the error of the
            # bright star's model, not its own wing (seen next to Alnitak).
            mmean = np.mean(sr.med, axis=0)
            with np.errstate(invalid="ignore"):
                dom = np.isfinite(sr.others) & (sr.others > NEIGHBOUR_DOM_FACTOR * np.abs(mmean))
            ok &= ~dom
            P[i, ok] = p[ok]
            Pc[i, ok] = (mc / (F * self.A))[ok]
            S[i, ok] = np.sqrt(st2[ok])
            SA[i] = sa
        # SPEC: the agreement term 0.921 sigma_agree p uses the per-ring
        # unweighted median p-hat, not the star's own p_i: with p_i the weights
        # 1/sigma_tot^2 ~ 1/p_i^2 favour exactly the stars whose rings came out
        # too low (off-centre or partly saturated), which biased the core by
        # ~100x on real data.
        import warnings
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            phat = np.nanmedian(np.where(np.isfinite(P), P, np.nan), axis=0)
        # SPEC (round 3): beyond 4 FWHM a star's ring is dropped where the star
        # is not expected to be significant (median profile p-hat below that
        # star's own error). Dozens of faint stars whose rings are pure noise
        # there otherwise swamp the few bright stars that do measure the wing,
        # and the reach walk stopped at ~0.5' on real data. p-hat, not the star's
        # own value, decides, so the selection does not bias the profile.
        far = self.rg.mid >= SECTOR_MIN_FWHM * self.fwhm
        # weighted median per ring (weights 1/S^2 from the errors before the
        # agreement term, which do not depend on p_i): dominated by the bright,
        # well-measured stars. SPEC (round 3): it is both the expected signal
        # for dropping insignificant rings and the level of the common
        # agreement floor. The unweighted median p-hat is ~0 at large radii in
        # a crowded field (dropping the bright stars too) and, where a few
        # contaminated faint stars remain, too high (inflating every star's
        # floor and cutting the reach at ~110" on M31 in live Siril).
        pw = np.full(self.rg.n, np.nan)
        for k in range(self.rg.n):
            okk = np.isfinite(P[:, k]) & np.isfinite(S[:, k]) & (S[:, k] > 0)
            if okk.any():
                pw[k] = weighted_median(P[okk, k], 1.0 / S[okk, k] ** 2)
        with np.errstate(invalid="ignore"):
            weak = far[None, :] & (np.abs(pw)[None, :] < S)
        P = np.where(weak, np.nan, P)
        Pc = np.where(weak, np.nan, Pc)
        S = np.where(weak, np.nan, S)
        lvl = np.where(np.isfinite(pw), np.abs(pw), np.abs(np.nan_to_num(phat)))
        S = np.sqrt(S ** 2 + (0.921 * SA[:, None] * lvl[None, :]) ** 2)
        return P, S, Pc

    @staticmethod
    def combine(P, S, min_stars=MIN_STARS_RING):
        n = P.shape[1]
        comb = np.full(n, np.nan)
        sig = np.full(n, np.nan)
        nst = np.zeros(n, int)
        reject = np.zeros(P.shape, bool)
        mins = np.broadcast_to(np.asarray(min_stars), (n,))
        for k in range(n):
            min_stars = int(mins[k])
            ok = np.isfinite(P[:, k]) & np.isfinite(S[:, k])
            if ok.sum() < min_stars:
                continue
            w = 1.0 / S[ok, k] ** 2
            m = weighted_median(P[ok, k], w)
            good = np.abs(P[ok, k] - m) <= RING_REJECT_SIGMA * S[ok, k]
            idx = np.nonzero(ok)[0]
            reject[idx[~good], k] = True
            if good.sum() < min_stars:
                continue
            m = weighted_median(P[ok, k][good], w[good])
            comb[k] = m
            sig[k] = MEDIAN_EFF / math.sqrt(float(np.sum(w[good])))
            nst[k] = int(good.sum())
        return comb, sig, nst, reject

    def r_meas(self, p, s):
        """Outer edge of the last ring before the first run of 3 consecutive
        insignificant rings, walking out from 2 FWHM (spec 8.3)."""
        rg = self.rg
        start = int(np.searchsorted(rg.mid, 2 * self.fwhm))
        last = None
        run = 0
        gap_start = None
        # SPEC (round 3): rings left undefined by the minimum-star rule are gaps,
        # not insignificant rings: a gap of up to a factor MAX_GAP_FACTOR in r is skipped, so a
        # crop or sparse field where few stars reach 4-10 FWHM still reaches the
        # sector-checked far rings of its bright stars.
        for k in range(start, rg.n):
            if not (np.isfinite(p[k]) and np.isfinite(s[k])):
                if gap_start is None:
                    gap_start = rg.lo[k]
                if rg.hi[k] > MAX_GAP_FACTOR * max(gap_start, 1e-9):
                    break
                continue
            gap_start = None
            if p[k] > 3 * s[k]:
                run = 0
                last = k
            else:
                run += 1
                if run >= 3:
                    break
        if last is None:
            return None, None
        return float(rg.hi[last]), last

    @staticmethod
    def monotone(p, start):
        q = p.copy()
        if q.size - start >= 3:
            seg = q[start:]
            sm = seg.copy()
            sm[1:-1] = np.median(np.vstack([seg[:-2], seg[1:-1], seg[2:]]), axis=0)
            q[start:] = np.minimum.accumulate(sm)
        return q

    @staticmethod
    def fill_core(r, prof, core):
        prof = np.asarray(prof, float).copy()
        bad = core & ~(np.isfinite(prof) & (prof > 0))
        good = np.isfinite(prof) & (prof > 0)
        if bad.any() and good.sum() >= 2:
            lr = np.log(np.maximum(r, 1e-6))
            prof[bad] = np.exp(np.interp(lr[bad], lr[good], np.log(prof[good])))
        return prof

    def smooth_profile(self, r, pL, sL, p_ch, s_ch):
        """SPEC (round 4): local quadratic regression of ln p on ln r with a
        Gaussian window of PROFILE_SMOOTH_DLNR, blended in over
        PROFILE_SMOOTH_FWHM, then resampled on a PROFILE_FINE_DLNR grid. The
        core keeps the measured shape. Each profile ends where it did."""
        r = np.asarray(r, float)
        lr = np.log(np.maximum(r, 1e-6))
        n_f = max(2, int(math.ceil((lr[-1] - lr[0]) / PROFILE_FINE_DLNR)) + 1)
        lf = np.linspace(lr[0], lr[-1], n_f)
        # keep the original nodes inside the core exactly
        lf = np.union1d(lf, lr[r < PROFILE_SMOOTH_FWHM[1] * self.fwhm])
        rf = np.exp(lf)
        rf[0], rf[-1] = r[0], r[-1]
        wblend = smoothstep((rf - PROFILE_SMOOTH_FWHM[0] * self.fwhm)
                            / ((PROFILE_SMOOTH_FWHM[1] - PROFILE_SMOOTH_FWHM[0]) * self.fwhm))
        d = (lf[:, None] - lr[None, :]) / PROFILE_SMOOTH_DLNR
        kern = np.exp(-0.5 * d * d)

        def one(p):
            p = np.asarray(p, float)
            pos = p > 0
            end = int(np.argmax(~pos)) if not pos.all() else p.size
            if end < 2:
                return np.interp(lf, lr, p)
            ll, lp = lr[:end], np.log(p[:end])
            raw = np.interp(lf, ll, lp)
            w = kern[:, :end]
            dx = ll[None, :] - lf[:, None]
            s0, s1, s2 = w.sum(1), (w * dx).sum(1), (w * dx * dx).sum(1)
            s3, s4 = (w * dx ** 3).sum(1), (w * dx ** 4).sum(1)
            t0, t1, t2 = (w * lp).sum(1), (w * dx * lp).sum(1), (w * dx * dx * lp).sum(1)
            A = np.stack([np.stack([s0, s1, s2], -1), np.stack([s1, s2, s3], -1),
                          np.stack([s2, s3, s4], -1)], -2)
            bb = np.stack([t0, t1, t2], -1)
            sm = raw.copy()
            ok = np.abs(np.linalg.det(A)) > 1e-12 * np.maximum(s0, 1e-300) ** 3
            if ok.any():
                sm[ok] = np.linalg.solve(A[ok], bb[ok][..., None])[:, 0, 0]
            # the local fit must not wander from the data near the ends
            sm = np.clip(sm, raw - 0.3, raw + 0.3)
            out = np.exp((1 - wblend) * raw + wblend * sm)
            out = np.where(rf <= r[end - 1] * (1 + 1e-9), out, 0.0)
            return out

        def mono(p):
            # monotone (non-increasing) beyond 2 FWHM: a cumulative minimum
            # only, the smoothed curve has no single-ring outliers to reject
            q = p.copy()
            s = int(np.searchsorted(rf, 2 * self.fwhm))
            if q.size - s >= 2:
                q[s:] = np.minimum.accumulate(q[s:])
            return q

        pL_f = mono(one(pL))
        sL_f = np.interp(lf, lr, np.asarray(sL, float))
        p_f = np.array([mono(one(pc_)) for pc_ in p_ch])
        s_f = np.array([np.interp(lf, lr, sc_) for sc_ in s_ch])
        return rf, pL_f, sL_f, p_f, s_f

    def build(self, rings, Fpred, saturated, sig_agree, sig_sys, wing_lum, level_factor):
        rg = self.rg
        report = self.report
        nc = self.nc
        info = {}
        # SPEC (round 3): at least 5 stars per ring within 10 FWHM, but beyond
        # it 1 star suffices: those rings are sector-checked (lower quartile of 8
        # sector medians), and only the brightest stars reach that far. Without
        # this the measured profile stopped at ~4' on Alnitak and the tail came
        # from the r^-2.5 joint fit, under-subtracting a measurably shallower wing.
        mins = np.where(rg.mid >= FAR_FWHM * self.fwhm, MIN_STARS_FAR, MIN_STARS_RING)
        PL, SL, PLc = self.per_star(rings, Fpred, sig_agree, sig_sys, -1)
        pL, sL, nL, _ = self.combine(PL, SL, mins)
        # SPEC (round 12): the central (azimuthal median) luminance profile,
        # combined with the same weights; it carries the shape for the
        # hand-over slope and the tail alpha, which the conservative value
        # tilts steep (its deficit against the median grows with radius where
        # rays and wedges dominate the sector scatter: 4% at 30-60 px, 8% at
        # 60-105, 20% at 105-200, 39% at 200-400 px on the M31 G = 4.5 star).
        pLc, _, _, _ = self.combine(PLc, SL, mins)
        pc = []
        sc = []
        for c in range(nc):
            P, S, _ = self.per_star(rings, Fpred, sig_agree, sig_sys, c)
            a, b_, _, _ = self.combine(P, S, mins)
            pc.append(a)
            sc.append(b_)
        pc, sc = np.array(pc), np.array(sc)
        # SPEC (round 3): the model is a conservative lower bound: beyond 4 FWHM
        # each combined ring is lowered by CONSERVATIVE_SIGMA of its error (at
        # most halved), so that profile noise errs towards under-correction.
        # SPEC (round 4): the shift is ramped in over 3-5 FWHM instead of
        # switching on at 4 FWHM, so it puts no step into the profile.
        # SPEC (round 12): only with PROFILE_SAFETY "quantile"; the "lowerbound"
        # rule makes its one shift per star ring and has none here.
        cons = smoothstep((rg.mid - (SECTOR_MIN_FWHM - 1) * self.fwhm) / (2 * self.fwhm))
        if PROFILE_SAFETY != "lowerbound":
            with np.errstate(invalid="ignore"):
                pL = np.where(np.isfinite(sL), np.maximum(pL - cons * CONSERVATIVE_SIGMA * sL, (1 - 0.5 * cons) * pL), pL)
                pc = np.where(np.isfinite(sc), np.maximum(pc - cons[None] * CONSERVATIVE_SIGMA * sc,
                                                          (1 - 0.5 * cons[None]) * pc), pc)
        info["profile_safety"] = PROFILE_SAFETY
        # bright / faint overlap ratio (diagnostic)
        sat = np.asarray(saturated, bool)
        ratio = float("nan")
        if sat.sum() >= 3 and (~sat).sum() >= 3:
            pu, su, _, _ = self.combine(PL[~sat], SL[~sat], 3)
            ps, ss, _, _ = self.combine(PL[sat], SL[sat], 3)
            # SPEC: only rings where both combinations are significant (> 3 sigma)
            # are compared; faint unsaturated rings are dominated by the
            # background otherwise and the ratio is meaningless.
            sel = (rg.mid >= 4 * self.fwhm) & (rg.mid <= 15 * self.fwhm) & np.isfinite(pu) & \
                np.isfinite(ps) & (pu > 3 * su) & (ps > 3 * ss)
            if sel.sum() >= 2:
                ratio = float(np.median(ps[sel] / pu[sel]))
        info["overlap_ratio"] = ratio
        rmeas, kmeas = self.r_meas(pL, sL)
        if rmeas is None:
            raise HardRefusal("The extended PSF could not be measured: no significant rings "
                              "beyond 2 FWHM. There may be too few usable stars, or the "
                              "image is not linear.")
        info["r_meas"] = rmeas
        # measured part, up to r_meas
        keep = np.arange(rg.n) <= kmeas
        keep &= np.isfinite(pL)
        r_s = list(rg.mid[keep])
        pL_s = list(pL[keep])
        sL_s = list(sL[keep])
        # --- beyond r_meas: p_joint, then a power law.
        # SPEC: the hand-over is continuous in value and slope. The anchor is a
        # straight-line fit of ln p against ln r over the measured rings in
        # [0.6 r_meas, r_meas]; beyond it the tail relaxes from the anchor
        # (value and slope) towards the level-corrected p_joint (or the power
        # law) over a short range: delta(x) = (d0 + (ds + d0/L) x) e^(-x/L),
        # x = ln(r/r_anchor), L = HANDOVER_L (0.3, a factor ~1.35 in r); the
        # slope mismatch ds is clamped to +-0.5 because the local slope is noisy. The spec's constant offset over
        # [0.5 r_meas, r_meas] is still computed and reported (level check, I5).
        r_s = list(r_s)
        info["joint_offset"] = None
        info["joint_used"] = False
        rm_arr = np.array(r_s)
        pm_arr = np.array(pL_s)
        # SPEC (round 12): the slopes (anchor slope here, alpha below) are
        # fitted on the central profile where it is defined; the level stays
        # the conservative one (lnp_a, pm_arr), so the tail starts where it
        # did and is only no longer tilted by the growing deficit.
        pcm = np.where(np.isfinite(pLc[keep]), pLc[keep], pm_arr)
        anc = (rm_arr >= 0.6 * rmeas) & (pcm > 0)
        if anc.sum() >= 3:
            sl, ic = np.polyfit(np.log(rm_arr[anc]), np.log(pcm[anc]), 1)
        else:
            sl, ic = -2.5, math.log(max(pm_arr[-1], 1e-300)) + 2.5 * math.log(rm_arr[-1])
        r_a = float(rm_arr[-1])
        lnp_a = math.log(max(float(pm_arr[-1]), 1e-300))   # value continuity at the last ring
        sl = min(sl, -0.5)                     # the wing must keep falling
        L = HANDOVER_L
        base = None                            # (ln r samples, ln p samples) of the target tail
        r_joint = rmeas
        if wing_lum is not None and wing_lum.usable and level_factor and np.isfinite(level_factor):
            pj = wing_lum.p * level_factor
            pjs = wing_lum.p_sigma * level_factor
            rj = wing_lum.r_mid
            ov = (rj >= 0.5 * rmeas) & (rj <= rmeas) & (pj > 0)
            if ov.sum() >= 2:
                lpm = np.interp(np.log(rj[ov]), np.log(rm_arr), np.log(np.maximum(pm_arr, 1e-300)))
                sm = np.interp(np.log(rj[ov]), np.log(rm_arr), np.array(sL_s) / np.maximum(pm_arr, 1e-300))
                d = lpm - np.log(pj[ov])
                wv = 1.0 / (sm ** 2 + (pjs[ov] / pj[ov]) ** 2 + 1e-12)
                off = float(np.sum(wv * d) / np.sum(wv))
                off_s = float(1.0 / math.sqrt(np.sum(wv)))
                info["joint_offset"] = (off, off_s)
                if abs(off) > 2 * off_s:
                    report.warn(f"the joint-fit wing and the measured rings disagree by "
                                f"{off:+.2f} in ln p ({abs(off) / off_s:.1f} sigma); the offset is applied")
                pj = pj * math.exp(off)
                pjs = pjs * math.exp(off)
                sig_ok = (pj > 2 * pjs) & (pj > 0) & (rj > rmeas)
                # p_joint is used while significant (contiguously from r_meas)
                last = None
                for k in np.nonzero(rj > rmeas)[0]:
                    if sig_ok[k]:
                        last = k
                    else:
                        break
                good = (pj > 0) & (rj >= 0.5 * rmeas)
                if last is not None:
                    good &= rj <= rj[last]
                    r_joint = float(wing_lum.edges_hi[last])
                    info["joint_used"] = True
                if good.sum() >= 2:
                    base = (np.log(rj[good]), np.log(pj[good]))
            else:
                report.info("p_joint has fewer than 2 samples in [0.5 r_meas, r_meas]; not used")
        elif wing_lum is not None and not wing_lum.usable:
            report.warn("the joint background/wing fit is degenerate (frame-filling glow or "
                        "too few identifiable wing bases): beyond the measured reach the "
                        "wing is a power-law extrapolation")
        info["r_joint"] = r_joint
        # power-law slope for beyond the joint range: last factor of 2 of the
        # measured (+joint) profile, alpha clamped to [2, 3.5]
        fitm = (rm_arr >= rm_arr[-1] / 2) & (pcm > 0)
        # SPEC (round 3): alpha is clamped to [1.2, 3.5] instead of [2, 3.5]: the
        # tail is truncated at maxradius, so alpha < 2 does not diverge, and real
        # wings (Alnitak) measured -1.1 to -1.4. The tail is still the lower of
        # this and the joint-fit wing. SPEC (round 12): fitted on the central
        # profile (see above).
        alpha = float(np.clip(-np.polyfit(np.log(rm_arr[fitm]), np.log(pcm[fitm]), 1)[0], ALPHA_MIN_TAIL, 3.5)) \
            if fitm.sum() >= 2 else 2.5

        def target(lr):
            """ln p of the target tail at ln r. SPEC (round 3): the lower of the
            level-corrected joint-fit wing and the measured power law from the
            anchor (alpha in [2, 3.5]), so that an uncertain tail errs low."""
            pl = lnp_a - alpha * (lr - math.log(r_a))
            if base is None:
                return pl
            lb, pb = base
            v = np.interp(lr, lb, pb)
            # beyond the joint samples: power law from the last joint value
            last_lr = lb[-1]
            v_last = pb[-1]
            vj = np.where(lr > last_lr, v_last - alpha * (lr - last_lr), v)
            return np.minimum(vj, pl)

        n_ext = max(1, int(math.ceil(math.log(self.maxradius / r_a) / RING_DLNR)))
        r_ext = r_a * np.exp(RING_DLNR * np.arange(1, n_ext + 1))
        r_ext[-1] = max(r_ext[-1], self.maxradius)
        x = np.log(r_ext / r_a)
        lr = np.log(r_ext)
        tgt = target(lr)
        t0 = float(target(np.array([math.log(r_a)]))[0])
        h = 1e-3
        tslope = float((target(np.array([math.log(r_a) + h]))[0] - t0) / h)
        d0 = lnp_a - t0
        ds = float(np.clip(sl - tslope, -0.5, 0.5))   # a noisy local slope must not tilt the tail
        delta = (d0 + (ds + d0 / L) * x) * np.exp(-x / L)
        p_ext = np.exp(tgt + delta)
        info["alpha"] = alpha
        info["handover"] = {"anchor_r": r_a, "anchor_slope": float(sl), "d0": float(d0), "dslope": float(ds)}
        r_arr = np.concatenate([rm_arr, r_ext])
        pL_arr = np.concatenate([pm_arr, p_ext])
        sL_arr = np.concatenate([np.array(sL_s), p_ext * 0.3])
        # --- chromaticity
        start_m = int(np.searchsorted(r_arr, 2 * self.fwhm))
        pL_mono = self.monotone(pL_arr, start_m)
        ratio_uv = []
        p_ch = np.zeros((nc, r_arr.size))
        s_ch = np.zeros((nc, r_arr.size))
        nmeas = int(keep.sum())
        mid_meas = rg.mid[keep]
        for c in range(nc):
            if nc == 1:
                ratio_uv.append((0.0, 0.0))
                p_ch[c] = pL_mono
                s_ch[c] = sL_arr
                continue
            pcm = pc[c][keep]
            scm = sc[c][keep]
            sel = (mid_meas >= 10 * self.fwhm) & np.isfinite(pcm) & (pcm > 0) & (pL[keep] > 0)
            if sel.sum() >= 1:
                y = np.log(pcm[sel] / pL[keep][sel])
                ws = 1.0 / ((scm[sel] / pcm[sel]) ** 2 + (sL[keep][sel] / pL[keep][sel]) ** 2 + 1e-6)
                u, v = float(np.sum(ws * y) / np.sum(ws)), 0.0
                if sel.sum() >= 3:
                    Xd = np.column_stack([np.ones(sel.sum()), np.log(mid_meas[sel])])
                    Wd = np.diag(ws)
                    try:
                        cov = np.linalg.inv(Xd.T @ Wd @ Xd)
                        uv = cov @ Xd.T @ Wd @ y
                        if abs(uv[1]) > 2 * math.sqrt(cov[1, 1]):
                            u, v = float(uv[0]), float(uv[1])
                    except np.linalg.LinAlgError:
                        pass
            else:
                # SPEC: no rings beyond 10 FWHM: the ratio is the flux-weighted
                # mean channel/luminance ratio of the inner rings
                okc = np.isfinite(pcm) & (pcm > 0) & (pL[keep] > 0)
                u = float(np.median(np.log(pcm[okc] / pL[keep][okc]))) if okc.any() else math.log(1.0)
                v = 0.0
            ratio_uv.append((u, v))
            ratio = np.exp(u + v * np.log(np.minimum(np.maximum(r_arr, 1e-6), rmeas)))
            outer = pL_mono * ratio
            inner = np.interp(np.log(r_arr), np.log(np.maximum(mid_meas, 1e-6)),
                              np.where(np.isfinite(pcm), pcm, np.nan), left=np.nan, right=np.nan)
            inner = np.where(np.isfinite(inner) & (r_arr <= rmeas), inner, outer)
            wb = smoothstep((r_arr - 8 * self.fwhm) / (4 * self.fwhm))
            p_ch[c] = (1 - wb) * inner + wb * outer
            s_ch[c] = sL_arr * ratio
            p_ch[c] = self.monotone(p_ch[c], start_m)
        # SPEC (round 4): ring-to-ring noise of the measured profile (slope
        # jumps of up to +-0.5 between 8% rings) was rendered as thin
        # concentric circles around the brightest stars, where the glow is
        # hundreds of sigma. Beyond 2-3.5 FWHM the profile is smoothed in
        # (ln r, ln p) and tabulated on a fine grid, so that it is continuous
        # in value and slope.
        # SPEC (round 7): non-positive (or NaN) samples inside the core
        # (r < 2 FWHM) are replaced by log-linear interpolation of the positive
        # ones, so that one bad core ring cannot end the whole profile
        core = r_arr < 2 * self.fwhm
        pL_mono = self.fill_core(r_arr, pL_mono, core)
        p_ch = np.array([self.fill_core(r_arr, q, core) for q in p_ch])
        info["core_r"] = 2 * self.fwhm
        r_f, pL_mono, sL_arr, p_ch, s_ch = self.smooth_profile(r_arr, pL_mono, sL_arr, p_ch, s_ch)
        r_arr = r_f
        # p(0): mean over r < 0.5 FWHM of the measured profile (spec 8.1)
        p0 = []
        sel0 = r_arr < 0.5 * self.fwhm
        if not sel0.any():
            sel0 = np.zeros(r_arr.size, bool)
            sel0[0] = True
        for c in range(nc):
            p0.append(float(np.mean(p_ch[c][sel0])))
        info.update(ratio_uv=ratio_uv, n_rings=nmeas, n_stars_lum=int(np.max(nL) if nL.size else 0))
        psf = RadialPSF(r_arr, p_ch, pL_mono, s_ch, sL_arr, p0=np.array(p0), meta=info)
        return psf, info


def psf_to_json(psf, params, geom_scale, fwhm_arcsec, r_ap_arcsec, source_image, zp, optics, chan_names):
    r = psf.r
    # SPEC: besides the spec's r_edges_arcsec, the exact sample radii are
    # stored as r_mid_arcsec (the profile is sampled at ring mid-radii).
    edges = np.concatenate([[0.0], np.sqrt(r[:-1] * r[1:]), [r[-1] * math.exp(RING_DLNR / 2)]])
    d = {
        "version": PSF_FILE_VERSION,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": f"GaiaGlowSubtraction {VERSION}",
        "source_image": source_image,
        "image_scale_arcsec": geom_scale,
        "fwhm_arcsec": fwhm_arcsec,
        "r_ap_arcsec": r_ap_arcsec,
        "units": "arcsec^-2 per calibrated flux",
        "lum": {"r_edges_arcsec": edges.tolist(), "r_mid_arcsec": r.tolist(),
                "profile": psf.p_lum.tolist(), "sigma": psf.sig_lum.tolist()},
        "channels": [{"name": chan_names[c], "r_edges_arcsec": edges.tolist(),
                      "r_mid_arcsec": r.tolist(), "profile": psf.p[c].tolist(),
                      "sigma": psf.sig[c].tolist(),
                      "ratio_u": psf.meta.get("ratio_uv", [(0, 0)] * psf.nc)[c][0],
                      "ratio_v": psf.meta.get("ratio_uv", [(0, 0)] * psf.nc)[c][1],
                      "p0": float(psf.p0[c])}
                     for c in range(psf.nc)],
        "r_meas": psf.meta.get("r_meas"), "r_joint": psf.meta.get("r_joint"),
        "alpha": psf.meta.get("alpha"), "zp": zp,
        "source": psf.meta.get("source", "measured"),
        "optics": optics,
        "parameters": params.full_text(),
    }
    return d


def load_psf_file(path, nc, fwhm_arcsec, optics, report, soft):
    """Load and validate a .ggspsf file (spec 8.4, 15.2 P6)."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        raise HardRefusal(f"The PSF file '{path}' cannot be read as JSON ({e}).")
    if not isinstance(d, dict) or d.get("version") != PSF_FILE_VERSION:
        raise HardRefusal(f"The PSF file '{path}' has an unknown version "
                          f"({d.get('version') if isinstance(d, dict) else '?'}).")
    try:
        chans = d["channels"]
        if len(chans) != nc:
            raise HardRefusal(f"The PSF file has {len(chans)} channels but the image has {nc}.")

        def arr(x):
            a = np.asarray(x, float)
            if not np.all(np.isfinite(a)):
                raise HardRefusal("The PSF file contains NaN or infinite values.")
            return a

        lum = d["lum"]
        r = arr(lum.get("r_mid_arcsec") or [])
        if r.size == 0:
            e = arr(lum["r_edges_arcsec"])
            r = np.sqrt(np.maximum(e[:-1], e[1] * 0.5) * e[1:])
        if r.size < 3 or np.any(np.diff(r) <= 0):
            raise HardRefusal("The PSF file has non-monotonic radii.")
        pL = arr(lum["profile"])
        sL = arr(lum.get("sigma", np.zeros(r.size)))
        p = np.array([arr(c["profile"]) for c in chans])
        sg = np.array([arr(c.get("sigma", np.zeros(r.size))) for c in chans])
        if p.shape[1] != r.size or pL.size != r.size:
            raise HardRefusal("The PSF file profile lengths do not match its radii.")
        p0 = np.array([float(c.get("p0", p[i][0])) for i, c in enumerate(chans)])
        rap = float(d["r_ap_arcsec"])
        ffw = float(d.get("fwhm_arcsec", 0) or 0)
    except HardRefusal:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise HardRefusal(f"The PSF file is malformed ({e}).")
    fo = d.get("optics", {}) or {}
    for key, label in (("telescop", "telescope"), ("instrume", "instrument")):
        a, b_ = str(fo.get(key, "") or "").strip(), str(optics.get(key, "") or "").strip()
        if a and b_ and a != b_:
            soft(f"The PSF file was measured with a different {label} ('{a}' vs '{b_}'). "
                 "A PSF from different optics will not match this image's glow.")
    fa, fb = float(fo.get("focallen_mm", 0) or 0), float(optics.get("focallen_mm", 0) or 0)
    if fa > 0 and fb > 0 and abs(fa - fb) / fb > 0.10:
        soft(f"The PSF file was measured at focal length {fa:.0f} mm, this image at {fb:.0f} mm.")
    a, b_ = str(fo.get("filter", "") or ""), str(optics.get("filter", "") or "")
    if a and b_ and a != b_:
        report.warn(f"PSF file filter '{a}' differs from this image's '{b_}'")
    if ffw > 0 and fwhm_arcsec > 0 and abs(ffw - fwhm_arcsec) / fwhm_arcsec > 0.30:
        report.warn(f"PSF file FWHM {ffw:.2f}\" differs from this image's {fwhm_arcsec:.2f}\" by more than 30%")
    meta = {"r_meas": d.get("r_meas"), "r_joint": d.get("r_joint"), "alpha": d.get("alpha"),
            "ratio_uv": [(c.get("ratio_u", 0), c.get("ratio_v", 0)) for c in chans], "loaded": path,
            "core_r": 2 * ffw if ffw > 0 else 0.0}
    return RadialPSF(r, p, pL, sg, sL, p0=p0, meta=meta), rap


# ===========================================================================
# 10. Star selection and flux refinement (spec 9.1, 9.2)
# ===========================================================================

def glow_radius(F, pfun, sigma, A_px, fwhm_arcsec, maxradius, nc, level=None):
    """R_glow,i = max over channels of the radius > 2 FWHM where
    F_c p_c(r) A_px falls below RGLOW_SIGMA * sigma_c (spec 9.1).
    Returns (R, capped)."""
    F = np.atleast_2d(F)
    n = F.shape[0]
    r_g = np.geomspace(2 * fwhm_arcsec, maxradius, 600)
    R = np.full(n, 2 * fwhm_arcsec)
    for c in range(nc):
        pg = np.maximum(pfun(r_g, c), 0)
        pos = np.nonzero(pg > 0)[0]
        if pos.size == 0:
            continue
        pg[:pos[0]] = pg[pos[0]]          # e.g. the generic wing starts at 3 FWHM
        pg = np.minimum.accumulate(pg)
        with np.errstate(divide="ignore"):
            t = (RGLOW_SIGMA if level is None else level) * sigma[c] / (np.maximum(F[:, c], 1e-300) * A_px)
        idx = np.searchsorted(-pg, -t, side="right")
        Rc = np.empty(n)
        lo = idx == 0
        hi = idx >= r_g.size
        mid = ~(lo | hi)
        Rc[lo] = 2 * fwhm_arcsec
        Rc[hi] = maxradius
        if np.any(mid):
            i1 = idx[mid]
            i0 = i1 - 1
            p0, p1 = pg[i0], pg[i1]
            with np.errstate(all="ignore"):
                f = np.where((p0 > 0) & (p1 > 0) & (p0 != p1),
                             (np.log(p0) - np.log(t[mid])) / (np.log(p0) - np.log(np.maximum(p1, 1e-300))), 0.5)
            f = np.clip(np.nan_to_num(f, nan=0.5), 0, 1)
            Rc[mid] = np.exp(np.log(r_g[i0]) + f * (np.log(r_g[i1]) - np.log(r_g[i0])))
        R = np.maximum(R, Rc)
    capped = R >= maxradius * (1 - 1e-9)
    return np.minimum(R, maxradius), capped


def select_casters(R, fwhm_arcsec, frame_dist, g, auto, faintG):
    inter = frame_dist < R
    if auto:
        return (R > SELECT_FWHM * fwhm_arcsec) & inter
    return (g <= faintG) & inter


def refine_flux(rings, Fpred_i, psf, A_px, rg, r_lo, R, sig_agree, sig_sys, tolerance,
                dim_max=REFINE_DIM_MAX, chans=None):
    """Fit a flux scale s on the luminance rings over [r_lo, R] (spec 9.2), within
    [-dim_max, +tolerance] mag. SPEC (round 15): chans restricts the fit to those
    channels (route-B stars are also refined per channel).
    Returns (s, n_rings, held_at_tolerance)."""
    if rings is None:
        return 1.0, 0, False
    ch = list(range(rings.med.shape[0])) if chans is None else list(chans)
    sel = rings.ok & (rg.mid >= r_lo) & (rg.mid <= R)
    sig_l = np.sum(rings.med[ch], axis=0)
    oth = rings.others
    with np.errstate(invalid="ignore"):
        dom = np.isfinite(oth) & (oth > NEIGHBOUR_MODEL_MAX * (sig_l / max(1, len(ch)) + oth))
    sel &= ~dom
    if sel.sum() < 5:
        return 1.0, int(sel.sum()), False
    model = np.zeros(rg.n)
    for c in ch:
        model += Fpred_i[c] * A_px * psf.eval(rg.mid, c)
    sg = np.sqrt(np.sum(rings.sig[ch] ** 2, axis=0)
                 + (0.921 * float(np.mean(np.asarray(sig_agree)[ch])) * model) ** 2
                 + float(np.sum(np.asarray(sig_sys)[ch] ** 2)))
    # SPEC: the spec's "too few rings" is extended to "too little signal": the
    # formal error of s must be below REFINE_MAX_SIGMA_S, otherwise s = 1. On
    # real data faint casters (glow fitted over 5-9 rings at a few sigma) gave
    # s anywhere from -1 to 35, i.e. local background and nebulosity, and half
    # of the refined stars sat at the tolerance limits.
    sig_s = 1.0 / math.sqrt(max(float(np.sum((model[sel] / sg[sel]) ** 2)), 1e-30))
    if sig_s > REFINE_MAX_SIGMA_S:
        return 1.0, -int(sel.sum()), False
    s_ = huber_scale(sig_l[sel], model[sel], sg[sel])
    if not np.isfinite(s_) or s_ <= 0:
        return 1.0, int(sel.sum()), False
    lo, hi = 10 ** (-0.4 * dim_max), 10 ** (0.4 * tolerance)
    held = s_ > hi or s_ < lo
    return float(np.clip(s_, lo, hi)), int(sel.sum()), held


# ===========================================================================
# 11. Glow rendering, own-light cap and core protection (spec 9.3, 9.4)
# ===========================================================================

def own_light_cap(model, img_minus_bg_coarse_L, valid_coarse, sigma_L, report):
    """Cap factor f on the coarse grid from the luminance (channel mean)
    model against the light present (spec 9.3). Returns (f_coarse, held)."""
    r = model.r
    # SPEC: "luminance" for the cap is the channel mean, for the model and the
    # image alike (the ratio f is the same as with a sum).
    GL = np.mean(model.coarse, axis=0)
    sm = ndimage.median_filter(np.nan_to_num(img_minus_bg_coarse_L, nan=0.0), size=3, mode="nearest")
    # inner zones of all stars are not capped. SPEC (round 4): the exemption
    # fades out over the outer quarter of the inner zone (weight 1 -> 0)
    # instead of ending at a hard circle at r_inner_px.
    inner = np.zeros(GL.shape, np.float32)
    yy, xx = np.meshgrid(r.yc, r.xc, indexing="ij")
    for st in model.stars:
        if not (-r.r_inner_px <= st.x <= r.w + r.r_inner_px and -r.r_inner_px <= st.y <= r.h + r.r_inner_px):
            continue
        j0 = max(0, int((st.y - r.r_inner_px) // r.b))
        j1 = min(r.Hc, int((st.y + r.r_inner_px) // r.b) + 2)
        i0 = max(0, int((st.x - r.r_inner_px) // r.b))
        i1 = min(r.Wc, int((st.x + r.r_inner_px) // r.b) + 2)
        if j0 < j1 and i0 < i1:
            d_ = np.hypot(xx[j0:j1, i0:i1] - st.x, yy[j0:j1, i0:i1] - st.y)
            w_ = 1.0 - smoothstep((d_ - 0.75 * r.r_inner_px) / (0.25 * r.r_inner_px))
            inner[j0:j1, i0:i1] = np.maximum(inner[j0:j1, i0:i1], w_)
    # SPEC: sigma_cap from adjacent-cell differences of the smoothed map over
    # star-free cells (valid cells where the model is < 0.1 sigma).
    free = valid_coarse & (GL < 0.1 * sigma_L) & np.isfinite(img_minus_bg_coarse_L)
    dx = (sm[:, 1:] - sm[:, :-1])[free[:, 1:] & free[:, :-1]]
    sigma_cap = mad_sigma(dx) / math.sqrt(2) if dx.size > 50 else sigma_L
    if not np.isfinite(sigma_cap) or sigma_cap <= 0:
        sigma_cap = sigma_L
    cap = np.maximum(0.0, sm) + CAP_K * sigma_cap
    with np.errstate(all="ignore"):
        f = np.where(GL > 0, np.minimum(1.0, cap / GL), 1.0)
    f = np.where(np.isfinite(f), f, 1.0)
    f = (inner + (1.0 - inner) * f).astype(np.float32)
    tot = float(np.sum(GL))
    held = float(np.sum((1 - f) * GL) / tot) if tot > 0 else 0.0
    return f, held, sigma_cap


def protection_mask(L_all, model, in_frame_idx, T_i, rdisc_px, fwhm_px, ctx=None):
    """Protection masks for all channels (spec 9.4). L_all is the
    channel-mean residual img - bg - total model. Returns (M, zone, per_star)
    with per_star = [(model index, y0, y1, x0, x1, M_i)]."""
    h, w = L_all.shape
    zone = np.zeros((h, w), bool)
    zones = []
    for n_i, i in enumerate(in_frame_idx):
        if ctx is not None and n_i % 20 == 0:
            ctx.check_cancel()
        st = model.stars[i]
        # SPEC (round 11): a caster whose centre lies just outside the frame (or in
        # an empty border) but whose core disc reaches into it is seeded at
        # the nearest frame pixel: that pixel is in its own core, so the
        # connected component found there is the right one.
        ix = min(w - 1, max(0, int(round(st.x))))
        iy = min(h - 1, max(0, int(round(st.y))))
        half = int(max(64, 4 * rdisc_px[n_i]))
        while True:
            x0, x1 = max(0, ix - half), min(w, ix + half + 1)
            y0, y1 = max(0, iy - half), min(h, iy + half + 1)
            X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
            own = np.mean(model.own_all(i, X, Y), axis=0)
            Li = L_all[y0:y1, x0:x1] + own
            above = Li > T_i[n_i]
            lab, _ = ndimage.label(above)
            L0 = lab[iy - y0, ix - x0]
            comp = (lab == L0) if L0 > 0 else np.zeros_like(above)
            touches = L0 > 0 and (comp[0].any() or comp[-1].any() or comp[:, 0].any() or comp[:, -1].any())
            if touches and half < 2048 and (x0 > 0 or y0 > 0 or x1 < w or y1 < h):
                half *= 2
                continue
            break
        disc = np.hypot(X - st.x, Y - st.y) <= rdisc_px[n_i]
        zi = comp | disc
        zone[y0:y1, x0:x1] |= zi
        zones.append((i, y0, y1, x0, x1, zi))
    M = np.ones((h, w), np.float32)
    per_star = []
    feather = 2.0 * fwhm_px
    marg = int(math.ceil(feather)) + 2
    # SPEC (round 3): one feathered mask per star. Star i's zone protects
    # only star i's own model; the spec's single mask M multiplied the total
    # model, so the zones of faint stars inside a bright star's glow left
    # discs of unsubtracted glow around them. The global M (minimum over the
    # stars) is kept for the checks and reports.
    for (i, y0, y1, x0, x1, zi) in zones:
        if not zi.any():
            continue
        yy_, xx_ = np.nonzero(zi)
        a0, a1 = max(0, y0 + yy_.min() - marg), min(h, y0 + yy_.max() + 1 + marg)
        b0, b1 = max(0, x0 + xx_.min() - marg), min(w, x0 + xx_.max() + 1 + marg)
        sub = np.zeros((a1 - a0, b1 - b0), bool)
        sy0, sx0 = max(a0, y0), max(b0, x0)
        sy1, sx1 = min(a1, y1), min(b1, x1)
        sub[sy0 - a0:sy1 - a0, sx0 - b0:sx1 - b0] = zi[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        d = ndimage.distance_transform_edt(~sub)
        Mloc = smoothstep(d / feather).astype(np.float32)
        per_star.append((i, a0, a1, b0, b1, Mloc))
        M[a0:a1, b0:b1] = np.minimum(M[a0:a1, b0:b1], Mloc)
    return M, zone, per_star


# ===========================================================================
# 12. Misuse checks helpers (spec 15)
# ===========================================================================

def icc_nonlinear(icc):
    """True if an ICC profile has a non-linear tone curve (rTRC/gTRC/kTRC)."""
    if not icc or len(icc) < 132:
        return False
    try:
        n = struct.unpack(">I", icc[128:132])[0]
        for k in range(min(n, 200)):
            sig, off, size = struct.unpack(">4sII", icc[132 + 12 * k:144 + 12 * k])
            if sig not in (b"rTRC", b"gTRC", b"bTRC", b"kTRC"):
                continue
            typ = icc[off:off + 4]
            if typ == b"curv":
                cnt = struct.unpack(">I", icc[off + 8:off + 12])[0]
                if cnt == 0:
                    continue
                if cnt == 1:
                    g = struct.unpack(">H", icc[off + 12:off + 14])[0] / 256.0
                    if abs(g - 1.0) > 0.01:
                        return True
                    continue
                return True
            if typ == b"para":
                g = struct.unpack(">i", icc[off + 12:off + 16])[0] / 65536.0
                if abs(g - 1.0) > 0.01:
                    return True
    except (struct.error, IndexError):
        return False
    return False


def history_has(history, words):
    out = []
    for line in history or []:
        low = str(line).lower()
        for wd in words:
            if re.search(r"(?<![a-z])" + re.escape(wd) + r"(?![a-z])", low):
                out.append(str(line))
                break
    return out


def interior_zero_fraction(img):
    z = np.all(img == 0, axis=0) if img.ndim == 3 else (img == 0)
    if not z.any():
        return 0.0
    lab, n = ndimage.label(z)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    if border:
        z &= ~np.isin(lab, list(border))
    return float(z.mean())


def cfa_phase_test(img_mono, sigma0):
    """2x2 phase test on a star-free central region (spec 15.1 I7)."""
    h, w = img_mono.shape
    s0 = min(512, h // 2 * 2, w // 2 * 2)
    y0, x0 = (h - s0) // 2 // 2 * 2, (w - s0) // 2 // 2 * 2
    reg = img_mono[y0:y0 + s0, x0:x0 + s0].astype(np.float64)
    med = np.median(reg)
    clip = reg < med + 3 * max(sigma0, 1e-12)
    meds = []
    for dy in (0, 1):
        for dx in (0, 1):
            sub = reg[dy::2, dx::2][clip[dy::2, dx::2]]
            meds.append(np.median(sub) if sub.size else med)
    n = clip.sum()
    spread = max(meds) - min(meds)
    return (spread > I7_SIGMA * sigma0 / math.sqrt(max(n / 4.0, 1))) and (spread > I7_REL * abs(med)), spread


def paint_circles(mask, xs, ys, rs):
    """Set mask True inside the circles (native px)."""
    h, w = mask.shape
    for x, y, r in zip(xs, ys, rs):
        if not (np.isfinite(x) and np.isfinite(y)) or r <= 0:
            continue
        x0, x1 = max(0, int(x - r)), min(w, int(x + r) + 2)
        y0, y1 = max(0, int(y - r)), min(h, int(y + r) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        Y, X = np.ogrid[y0:y1, x0:x1]
        mask[y0:y1, x0:x1] |= (X - x) ** 2 + (Y - y) ** 2 <= r * r


def paint_ellipses(mask, geom, xs, ys, r_arcsec):
    h, w = mask.shape
    for x, y, r in zip(xs, ys, r_arcsec):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        ex, ey = geom.px_extent(r)
        x0, x1 = max(0, int(x - ex)), min(w, int(x + ex) + 2)
        y0, y1 = max(0, int(y - ey)), min(h, int(y + ey) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        Y, X = np.mgrid[y0:y1, x0:x1]
        mask[y0:y1, x0:x1] |= geom.r_arcsec(X - x, Y - y) < r


# ===========================================================================
# 13. Orchestration and report
# ===========================================================================

class RunContext:
    """Glue between the numerical core and the user interface."""

    def __init__(self, io, params, report, ui=None, cancel_event=None):
        self.io = io
        self.params = params
        self.report = report
        self.ui = ui                     # None in the CLI
        self.cancel_event = cancel_event or threading.Event()

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled("cancelled by the user")

    def progress(self, msg, frac):
        try:
            self.io.progress(msg, frac)
        except Exception:
            pass
        # SPEC (round 11): the window's progress bar follows the run itself
        if self.ui is not None and hasattr(self.ui, "progress"):
            try:
                self.ui.progress(frac)
            except Exception:
                pass

    def soft(self, msg):
        """Soft refusal (spec 15): GUI asks, CLI needs -force."""
        if self.ui is not None:
            if not self.ui.ask("soft", msg):
                raise SoftRefusal(msg)
            self.report.warn("run anyway after: " + msg)
        elif self.params.force:
            self.report.warn("-force given, proceeding despite: " + msg)
        else:
            raise SoftRefusal(msg + " (use -force to proceed anyway)")

    def download_budget(self, mb):
        lim = download_limit_mb(self.params, getattr(self, "download_estimate", None))
        if mb <= lim:
            return
        kind = "automatic limit" if self.params.maxdownload in (None, "auto") else "limit"
        msg = (f"The remote Gaia catalogue download for this field is {mb:.1f} MB, above the "
               f"{kind} of {lim:.0f} MB.")
        if self.ui is not None:
            if not self.ui.ask("download", msg + " Download it?"):
                raise Cancelled("download declined")
        else:
            raise HardRefusal(msg + " Raise -maxdownload (MB) to allow it.")


def apply_amount(out_full, glow_full, amount, inplace=False):
    """SPEC (round 21): the amount scales the glow that the safety stages
    produced at amount 1. The result is out_full + (1 - amount) * glow_full:
    it only gives light back (glow >= 0), so it cannot create undershoot or a
    dip, and a viewer can change the amount without a recompute. Amount 1
    returns the inputs unchanged."""
    if amount >= 1.0:
        return out_full, glow_full
    a = np.float32(amount)
    if inplace:
        for c in range(glow_full.shape[0]):     # per channel: one temporary frame
            out_full[c] += glow_full[c] * (np.float32(1.0) - a)
            glow_full[c] *= a
        return out_full, glow_full
    glow = glow_full * a
    out = out_full + glow_full * (np.float32(1.0) - a)
    return out, glow


@dataclass
class Result:
    out: np.ndarray = None          # internal float32 units
    glow: np.ndarray = None         # amount * (safe glow at amount 1), internal units
    summary: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    psf_json: dict = None
    label: str = ""
    fingerprint: dict = None
    numbers: dict = field(default_factory=dict)


class GlowSubtractor:
    """Runs the pipeline of spec 11 on the image provided by `io`."""

    def __init__(self, io, params, ctx):
        self.io = io
        self.p = params
        self.ctx = ctx
        self.R = ctx.report
        self.eta = ETA
        self.hist_bgx = False

    # -- small helpers -----------------------------------------------------
    def stage(self, msg, frac):
        self.ctx.check_cancel()
        self.R.info(f"[{self.R.elapsed():6.1f}s] {msg}")
        self.ctx.progress(f"GaiaGlowSubtraction: {msg}", frac)

    def cfg(self, group, key):
        try:
            return self.io.config(group, key)
        except Exception:
            return None

    # -- step 0: checks before any work ------------------------------------
    def preflight(self, info):
        p, R, ctx = self.p, self.R, self.ctx
        kw = info["keywords"]
        hist = info["history"]
        hdr = info["header"]
        if hdr is None:
            raise HardRefusal("The image has no FITS header (non-FITS source). Save it as FITS "
                              "and plate solve it again.")
        has_ct = all(k in hdr for k in ("CTYPE1", "CTYPE2"))
        has_cd = all(k in hdr for k in ("CD1_1", "CD2_2")) or \
            (all(k in hdr for k in ("CDELT1", "CDELT2")))
        if not (has_ct and has_cd):
            raise HardRefusal("The image is not plate solved (no WCS in its header). Plate solve "
                              "first (Tools > Astrometry), then rerun.")
        fn = info.get("filename") or ""
        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        if (info.get("orig_bitpix") is not None and int(info["orig_bitpix"]) == 8) or ext in I9_EXTS:
            raise HardRefusal("8-bit images are display exports and are not linear. Use the "
                              "32-bit or 16-bit stacked FITS image.")
        itype = str(getattr(kw, "image_type", "") or hdr.get("IMAGETYP", "") or "").lower()
        if any(t in itype for t in I8_CAL_TYPES):
            raise HardRefusal(f"This is a calibration frame (IMAGETYP '{itype}'). Glow subtraction "
                              "works on stacked light images.")
        stackcnt = int(getattr(kw, "stackcnt", 0) or 0)
        live = float(getattr(kw, "livetime", 0) or 0)
        expo = float(getattr(kw, "exposure", 0) or 0)
        if stackcnt == 1 or (stackcnt == 0 and expo > 0 and abs(live - expo) < 1e-6 and expo <= I8_SINGLE_EXP):
            R.warn("This looks like a single sub-exposure: it is noisy and the result will be weak. "
                   "The tool is intended for stacked images.")
        bayer = str(getattr(kw, "bayer_pattern", "") or "").strip()
        if info["nc"] == 1 and bayer:
            raise HardRefusal(f"The image is an undebayered CFA image (BAYERPAT {bayer}). Debayer first.")
        st = history_has(hist, STRETCH_HISTORY)
        if st:
            R.warn(f"HISTORY suggests the image was stretched ('{st[0]}'). Glow subtraction needs "
                   "linear data; run it before any stretch.")
        if icc_nonlinear(info.get("icc")):
            R.warn("The image has an ICC profile with a non-linear tone curve. Make sure the "
                   "pixel data are linear.")
        bx = history_has(hist, I5_HISTORY)
        if bx:
            self.hist_bgx = True
            R.warn(f"HISTORY shows background extraction was already applied ('{bx[0]}'). Part of "
                   "the glow may already be removed, so the full model can over-subtract. Run "
                   "this tool before background extraction.")
        dc = history_has(hist, I14_HISTORY)
        if dc:
            R.warn(f"HISTORY suggests deconvolution or star processing ('{dc[0]}'). Run this tool "
                   "before deconvolution and star reduction.")
        if history_has(hist, ("drizzle",)):
            self.eta = ETA_DRIZZLE
            R.info("Drizzled image: correlated-noise factor eta raised to 3")
        prev = [h for h in (hist or []) if str(h).startswith(LABEL_PREFIX + " ")]
        if prev:
            m = re.search(r"a=([0-9.]+)", prev[-1])
            ctx.soft(f"GaiaGlowSubtraction was already applied to this image (amount "
                     f"{m.group(1) if m else '?'}). Applying it again subtracts the glow twice. "
                     "Undo is the remedy.")
        # parameters
        if p.protect < P2_LOW:
            R.warn(f"-protect={p.protect:g} is very low: core subtraction likely; star cores may "
                   "become dark rings.")
        if p.tolerance > P3_TOL:
            R.warn(f"-tolerance={p.tolerance:.2f} is high: stars may be brightened to absorb "
                   "nebulosity as glow.")
        if p.catsource != "auto":
            R.warn(f"TESTING OPTION: -catsource={p.catsource} overrides the catalogue priority.")
        if p.auto and p.faintG != GlowParams().faintG:
            R.warn("-faintG has no effect while -auto is on.")
        if p.psf not in ("measure", "selection") and p.savepsf:
            R.warn("-savepsf has no effect when a PSF file is loaded with -psf.")

    def check_outputs(self, info):
        """P7: never overwrite without consent."""
        targets = []
        if self.p.savepsf:
            targets.append(self.p.savepsf)
        if self.p.glowimage:
            targets.append(self.glow_path(info))
        for t in targets:
            if t and os.path.exists(t):
                if self.ctx.ui is not None:
                    if not self.ctx.ui.ask("overwrite", f"'{t}' exists. Overwrite it?"):
                        raise Cancelled("overwrite declined")
                elif not self.p.overwrite:
                    raise HardRefusal(f"'{t}' already exists. Use -overwrite to replace it.")
            if info.get("filename") and os.path.abspath(t) == os.path.abspath(info["filename"]):
                raise HardRefusal("The output file would overwrite the input image.")

    def glow_path(self, info):
        fn = info.get("filename") or ""
        base = os.path.splitext(os.path.basename(fn))[0] or "image"
        d = os.path.dirname(fn) if fn and os.path.isdir(os.path.dirname(fn)) else (self.io.workdir() or ".")
        return os.path.join(d, f"{base}_glow.fit")

    # -- main computation --------------------------------------------------
    def compute(self):
        """SPEC (round 8): Siril's rectangle selection is recorded and cleared
        before any full-image work (findstar honours it in the GUI, which
        confined the detections to the rectangle and false-fired I3), and
        restored at the end; the star overlay left by findstar is cleared
        (clearstar) at the end, also after an error or a cancel."""
        io = self.io
        self.user_sel = None
        if hasattr(io, "selection"):
            self.user_sel = io.selection()
            if self.user_sel is not None:
                if hasattr(io, "clear_selection") and not io.clear_selection():
                    self.R.warn("Siril's selection could not be cleared: star detection may be limited "
                                "to it. Clear it in Siril if the run fails.")
                self.R.info(f"Siril selection {self.user_sel} recorded"
                            + (" for the PSF" if self.p.psf == "selection" else "")
                            + " and cleared for the run (restored at the end)")
        try:
            return self._compute()
        finally:
            try:
                if getattr(io, "findstar_ran", False) and hasattr(io, "clear_stars"):
                    io.clear_stars()
                if self.user_sel is not None and hasattr(io, "restore_selection"):
                    io.restore_selection(self.user_sel)
            except Exception:
                pass

    def _compute(self):
        p, R, ctx, io = self.p, self.R, self.ctx, self.io
        self.stage("checking the image", 0.01)
        info = io.image_info()
        self.info = info
        self.preflight(info)
        self.check_outputs(info)
        raw = io.pixel_data()
        if raw.ndim == 2:
            raw = raw[None]
        nc, h, w = raw.shape
        info["nc"] = nc
        self.native_dtype = raw.dtype
        self.fp_start = image_fingerprint(raw, info.get("filename"))
        prev = io.load_last_fingerprint()
        if prev and fingerprints_match(prev.get("output"), self.fp_start):
            ctx.soft(f"This image matches the last output of GaiaGlowSubtraction (amount "
                     f"{prev.get('amount', '?')}). Applying it again subtracts the glow twice. "
                     "Undo is the remedy.")
        # SPEC (round 6): empty (fill) borders, e.g. unaligned channels
        self.border = detect_fill_borders(raw)
        msg = describe_fill_borders(self.border)
        if msg:
            if self.border["depth"] < BORDER_MIN_DEPTH:
                R.info(msg + " (only a thin edge: ignored)")
            else:
                ctx.soft(msg)
        # SPEC (round 18): the estimate follows the measured peak, which lies in
        # the final per-channel loop of render_and_protect: the image, output
        # and glow (3 nc frames), the background, GLsum, M and f_up (4), the
        # loop's want, cap, net, model and smooth-minimum temporaries (6), the
        # masks (7 bool frames ~ 2) plus a nominal 1 for the model patches and
        # protection masks (casters are not known yet), the empty-border sum
        # table if there is one (int32), and ~0.6 GB of interpreter, libraries,
        # catalogue and retained heap. 1.2.2 estimated 4 w h (nc + 4), 4-7x below
        # its peak. Measured peaks (1.2.3): M31 mono 24 Mpx 2.32 GB (estimate
        # 2.16), Alnitak RGB 24 Mpx 2.71 GB (2.69), bubble RGB 26 Mpx 3.40 GB (2.99).
        fill_px = 1 if self.border.get("depth", 0) > 0 else 0
        need = 4.0 * w * h * (3 * nc + 13 + fill_px) + 0.6e9
        avail = available_memory_bytes()
        if avail:
            if need > R5_SOFT * avail:
                ctx.soft(f"The run needs about {need / 1e9:.1f} GB of memory, more than 80% of the "
                         f"{avail / 1e9:.1f} GB available.")
            elif need > R5_WARN * avail:
                R.warn(f"The run needs about {need / 1e9:.1f} GB of memory ({avail / 1e9:.1f} GB available).")
        unit = 1.0 / 65535.0 if raw.dtype == np.uint16 else 1.0
        img = raw.astype(np.float32)
        if unit != 1.0:
            img *= unit
        del raw
        self.rescale = 1.0
        mx = float(np.nanmax(img))
        if self.native_dtype != np.uint16:
            if mx > I10_MAX:
                self.rescale = mx
                img /= mx
                R.warn(f"Float data outside [0, 1] (max {mx:.4g}); rescaled internally and written "
                       "back in the original scaling.")
        self.unit = unit / self.rescale
        self.img = img
        self.nc, self.h, self.w = nc, h, w
        zf = interior_zero_fraction(img)
        if zf > I11_ZERO_FRAC:
            R.warn(f"{100 * zf:.1f}% of the interior pixels are exactly zero (clipped shadows): "
                   "background and glow measurements will be biased.")
        # ---- geometry
        self.stage("geometry", 0.04)
        geom = ImageGeometry(info["header"], (h, w))
        # SPEC (round 7): empty borders are excluded from every statistic, ring,
        # fit and calibration-star choice, and are left unchanged by the
        # subtraction
        self.fill = self.border["mask"] if self.border["depth"] > 0 else None
        geom.set_fill(self.fill)
        self.geom = geom
        R.info(f"Image {w} x {h} x {nc}, scale {geom.scale:.3f}\"/px, "
               f"diagonal {2 * geom.half_diag_deg:.2f} deg, SIP {'yes' if geom.has_sip else 'no'}")
        R.number("scale", geom.scale)
        if geom.scale > SCALE_WARN_ARCSEC:
            R.warn(f"Image scale {geom.scale:.1f}\"/px is coarse (> 6\"/px): the PSF core is undersampled.")
        diag = 2 * geom.half_diag_deg
        if diag > I17_SOFT_DEG:
            ctx.soft(f"Very wide field ({diag:.1f} deg diagonal): the linear WCS is unreliable "
                     "outside the frame and the radial model will be poor.")
        elif diag > I17_WARN_DEG:
            R.warn(f"Wide field ({diag:.1f} deg): off-frame casters are limited to 0.25 x diagonal.")
        kw = info["keywords"]
        try:
            pix_um = float(getattr(kw, "pixel_size_x", 0) or 0)
            binx = int(getattr(kw, "binning_x", 1) or 1)
            fl = float(getattr(kw, "focal_length", 0) or 0)
            if pix_um > 0 and fl > 0:
                native_scale = 206.265 * pix_um * binx / fl
                if geom.scale < I12_SCALE_RATIO * native_scale and self.eta < ETA_DRIZZLE:
                    self.eta = ETA_DRIZZLE
                    R.info(f"Pixel scale {geom.scale:.2f}\" is below half the sensor scale "
                           f"{native_scale:.2f}\": drizzled/upsampled data assumed, eta = 3")
        except Exception:
            pass
        # ---- detections
        self.stage("star detection", 0.06)
        dets = []
        for c in range(nc):
            ctx.check_cancel()
            dets.append(io.detections(c, self.unit, nc, h))
        alld = [d for dc in dets for d in dc]
        fw = []
        for c in range(nc):
            v = [d.fwhm for d in dets[c] if not d.saturated and d.fwhm > 0]
            if v:
                fw.append(float(np.median(v)))
        if not fw:
            fw = [3.0]
            R.warn("No unsaturated star detections: FWHM assumed 3 px.")
        self.fwhm_px = float(np.median(fw))
        self.fwhm = self.fwhm_px * geom.scale
        rnd = [d.roundness for d in alld if not d.saturated]
        mr = float(np.median(rnd)) if rnd else 1.0
        R.info(f"Detections: {', '.join(str(len(d)) for d in dets)} per channel; FWHM "
               f"{self.fwhm_px:.2f} px ({self.fwhm:.2f}\"); roundness {mr:.2f}")
        if mr < I13_SOFT:
            ctx.soft(f"Stars are strongly elongated (roundness {mr:.2f}): the radial model will "
                     "leave large residuals.")
        elif mr < I13_WARN:
            R.warn(f"Stars are elongated (roundness {mr:.2f}): the radial model will leave residuals.")
        self.sat = np.ones(nc)
        for c in range(nc):
            self.sat[c], src = saturation_level(img[c], dets[c])
        self.lin = LIN_FRACTION * self.sat
        R.info("Saturation levels " + ", ".join(f"{v:.4f}" for v in self.sat))
        sig0 = []
        for st in info["stats"]:
            sig0.append(float(getattr(st, "bgnoise", 0.0) or 0.0) * self.unit if st is not None else 0.0)
        for c in range(nc):
            if not sig0[c] > 0:
                sub = img[c][::7, ::7]
                if self.fill is not None:
                    sub = sub[~self.fill[::7, ::7]]
                sig0[c] = mad_sigma(sub[np.isfinite(sub) & (sub != 0)])
        self.sig0 = np.array(sig0)
        if nc == 1:
            cfa, spread = cfa_phase_test(img[0], self.sig0[0])
            if cfa:
                raise HardRefusal("The image shows a 2x2 Bayer pattern (undebayered CFA data). "
                                  "Debayer first.")
        # ---- catalogue
        self.stage("catalogue", 0.10)
        ra_c, dec_c = float(geom.center[0][0]), float(geom.center[1][0])
        roff = p.maxradius / 60.0
        if diag > I17_WARN_DEG:
            roff = min(roff, I17_OFF_FRACTION * diag)
        r_cone = geom.half_diag_deg + roff
        date_obs = getattr(kw, "date_obs", None)
        epoch = julian_year(date_obs) if isinstance(date_obs, datetime) else None
        if epoch is None:
            R.info("No DATE-OBS: catalogue positions are used at epoch J2016.0")
        udd = io.userdatadir()
        est = estimate_xp_download(info["header"], (h, w), self.cfg, udd)
        ctx.download_estimate = est
        if est is not None:
            if est["local"]:
                R.info("Remote catalogue: not needed (local XP installed)")
            else:
                R.info(f"Remote catalogue estimate: ~{est['need_mb']:.0f} MB "
                       f"({est['cached_mb']:.0f} MB cached; {est['method']}); download limit "
                       f"{download_limit_mb(p, est):.0f} MB")
        cat = CatalogueService(ctx, self.cfg("core", "catalogue_gaia_astro"),
                               self.cfg("core", "catalogue_gaia_photo"),
                               os.path.join(udd, "spcc-cache") if udd else None, p.catsource)
        self.cat = cat
        a_s, b_s = cat.summary()
        R.info(f"Catalogue: astrometric {a_s}; local XP {b_s}; remote mirror {REMOTE_MIRRORS[0]}")
        table = cat.positions(ra_c, dec_c, r_cone, epoch)
        self.offline = table is None or len(table) == 0
        if self.offline:
            self.dets, self.alld = dets, alld
            return self.compute_offline(info)
        # SPEC (round 16): the bright-star table is loaded (cache) or built (VizieR) only
        # once the Gaia positions are in hand: the offline fallback does not use it.
        # -catsource=local means no network here too; the other values allow the one
        # small query. A missing table is never a refusal (-offline-ok does not apply):
        # without it the bright stars are under-corrected, never over-subtracted.
        cat.supplement = BrightStarSupplement(
            load_bright_table(udd, io.systemdatadir(), p.catsource != "local", R))
        table, dinfo = cat.add_supplement(table, ra_c, dec_c, r_cone, epoch)
        R.info(f"Catalogue stars in the {r_cone * 60:.0f}' cone: {len(table)} (G <= {G_KEEP_MAX}), "
               f"{dinfo['added']} added from the bright-star table (Hipparcos, V < {BRIGHT_VMAX})")
        # SPEC (round 15)
        if dinfo["cone"]:
            R.info(f"Bright-star table: {dinfo['cone']} stars in the cone, {dinfo['matched']} matched to "
                   f"Gaia, {dinfo['route_b'] + dinfo['added']} take their flux from Hipparcos (route B, "
                   f"G < {HIP_ROUTE_GMAX:.1f} or missing from Gaia); {dinfo['dropped']} Gaia companions "
                   f"within {HIP_COMBINED_ARCSEC:.0f}\" dropped (in the Hipparcos combined light)")
        R.number("bright_table", dinfo)
        xs, ys = geom.world2pix(table.ra, table.dec)
        inside = geom.in_frame(xs, ys) & np.isfinite(xs)
        # ---- I6 starless, then I3 astrometric check
        nref_mask = inside & (table.g <= 14.0) & geom.in_frame(xs, ys, EDGE_FWHM * self.fwhm_px)
        n_ref = int(nref_mask.sum())
        if n_ref >= 10 and len(alld) < I6_DET_FRACTION * n_ref:
            order = np.argsort(np.where(inside, table.g, 99))[:5]
            cores = 0
            for i in order:
                ix, iy = int(round(xs[i])), int(round(ys[i]))
                r = int(max(2, self.fwhm_px))
                y0, y1, x0, x1 = max(0, iy - 8 * r), min(h, iy + 8 * r), max(0, ix - 8 * r), min(w, ix + 8 * r)
                loc = img[:, y0:y1, x0:x1]
                pk = img[:, max(0, iy - r):iy + r + 1, max(0, ix - r):ix + r + 1]
                if pk.size and np.nanmax(pk) > np.nanmedian(loc) + I6_CORE_SIGMA * np.max(self.sig0):
                    cores += 1
            if cores == 0:
                raise HardRefusal("This looks like a starless image: stars are needed to calibrate "
                                  "and locate the glow. Run this before star removal (the result "
                                  "can be star-removed afterwards).")
        ac = astrometric_check(geom, xs, ys, table.g, [d for d in dets[min(1, nc - 1)]], self.fwhm_px)
        R.info(f"Star positions: {ac['n_match']} matches, median offset ({ac['dx']:+.2f}, "
               f"{ac['dy']:+.2f}) px, RMS {ac['rms']:.2f} px, match fraction "
               f"{100 * ac['fraction']:.0f}% of {ac['n_ref']} reference stars")
        R.number("astrometry", ac)
        if ac["n_match"] < I3_MIN_MATCHES or ac["fraction"] < I3_MIN_FRACTION or \
                not (ac["rms"] <= I3_MAX_RMS):
            # SPEC (addition): before blaming the solution, test the hypothesis
            # of a row-order convention error in the detections (y flipped). If
            # that matches, it is an internal error, not a bad plate solution.
            flipped = [Detection(x=d.x, y=h - 1 - d.y, fwhm=d.fwhm, roundness=d.roundness, peak=d.peak,
                                 saturated=d.saturated, sat=d.sat, channel=d.channel)
                       for d in dets[min(1, nc - 1)]]
            acf = astrometric_check(geom, xs, ys, table.g, flipped, self.fwhm_px)
            if acf["fraction"] >= I3_MIN_FRACTION and acf["n_match"] >= I3_MIN_MATCHES:
                raise HardRefusal("Internal error: the star detections only match the catalogue when "
                                  "flipped vertically (a row-order convention problem between Siril "
                                  "and this script, not a bad plate solution). Please report this "
                                  f"with your Siril and sirilpy versions (flipped: {acf['n_match']} "
                                  f"matches, {100 * acf['fraction']:.0f}%).")
            # SPEC (round 8): detections confined to a sub-region (e.g. findstar
            # ran on an active selection) are reported as such
            dd = dets[min(1, nc - 1)]
            if len(dd) >= 3:
                dx_ = np.array([d.x for d in dd]); dy_ = np.array([d.y for d in dd])
                bfrac = ((dx_.max() - dx_.min()) * (dy_.max() - dy_.min())) / float(w * h)
            else:
                bfrac = 0.0
            if bfrac < I3_DET_AREA_MIN:
                raise HardRefusal(
                    f"Star detection returned stars only in a small part of the frame ({100 * bfrac:.0f}% of "
                    f"its area; {ac['n_match']} matches, {100 * ac['fraction']:.0f}% of reference stars). "
                    "Siril's star finder was probably limited to a selection: clear the selection "
                    "in Siril and run again. The plate solution was not tested.")
            raise HardRefusal(f"The astrometric solution does not match the stars in this image "
                              f"({ac['n_match']} matches, {100 * ac['fraction']:.0f}% of reference "
                              f"stars found, RMS {ac['rms']:.2f} px). Re-solve the image.")
        if ac["rms"] > I3_WARN_RMS:
            R.warn(f"Astrometric RMS {ac['rms']:.2f} px is high (1-2 px).")
        if math.hypot(ac["dx"], ac["dy"]) > OFFSET_APPLY_PX:
            xs = xs + ac["dx"]
            ys = ys + ac["dy"]
        x_pre, y_pre = None, None
        # ---- polynomial astrometric refinement.
        # SPEC (I3 extension, user decision): Siril's own SIP solution is the
        # primary one. A linear-only solution gets a warning recommending a
        # polynomial re-solve, and the internal cubic correction (the spec's
        # deferred refinement) is applied. With SIP present the correction is
        # applied only if the residual RMS against bright isolated detections
        # still exceeds ASTROM_SIP_OK_RMS.
        ref_dets = dets[min(1, nc - 1)]
        if not geom.has_sip:
            R.warn(LINEAR_WCS_MSG)
            xs, ys, ainfo = astrometric_refinement(xs, ys, table.g, ref_dets, geom)
            if ainfo["n"]:
                R.info(f"Internal astrometric correction (cubic): {ainfo['n']} stars, RMS "
                       f"{ainfo['rms_before']:.2f} -> {ainfo['rms_after']:.2f} px")
        else:
            _, _, ainfo = astrometric_refinement(xs, ys, table.g, ref_dets, geom, apply=False)
            if ainfo["n"] and ainfo["rms_before"] > ASTROM_SIP_OK_RMS:
                xs, ys, ainfo = astrometric_refinement(xs, ys, table.g, ref_dets, geom)
                R.warn(f"The SIP solution leaves an RMS of {ainfo['rms_before']:.2f} px against "
                       f"{ainfo['n']} stars; an internal cubic correction was applied (RMS "
                       f"{ainfo['rms_after']:.2f} px). Consider re-solving the image.")
            elif ainfo["n"]:
                R.info(f"SIP solution residual RMS {ainfo['rms_before']:.2f} px against {ainfo['n']} "
                       "bright isolated stars: no internal correction needed")
        R.number("astrometric_refinement", ainfo)
        x_pre, y_pre = xs.copy(), ys.copy()
        # ---- unsaturated stars: place on matched detections (SPEC deviation)
        xs, ys, nmov, medshift = recentre_on_detections(xs, ys, table.g, ref_dets,
                                                        geom.in_frame(xs, ys) & np.isfinite(xs))
        R.info(f"{nmov} in-frame stars placed on their matched detections (median shift "
               f"{medshift:.2f} px)")
        # ---- saturated stars: recentre, saturated disc
        lab, nlab = saturated_regions(img, self.lin)
        bright = np.nonzero(inside & (table.g < 13.0))[0]
        order = bright[np.argsort(table.g[bright])]
        xs, ys, rsat = recentre_saturated(lab, nlab, xs, ys, order, geom)
        self.sat_lab = lab
        del lab
        self.table, self.xs, self.ys, self.rsat = table, xs, ys, rsat
        with np.errstate(invalid="ignore"):
            self.recentred = (np.abs(xs - x_pre) > 1e-9) | (np.abs(ys - y_pre) > 1e-9)
        self.inside = geom.in_frame(xs, ys) & np.isfinite(xs)
        self.frame_dist = geom.frame_distance_arcsec(xs, ys)
        self.dets = dets
        self.alld = alld
        return self.compute_main(info)

    def compute_main(self, info):
        p, R, ctx, io = self.p, self.R, self.ctx, self.io
        geom, img, nc, h, w = self.geom, self.img, self.nc, self.h, self.w
        kw = info["keywords"]
        table, xs, ys, cat = self.table, self.xs, self.ys, getattr(self, "cat", None)
        # ---- spectra and synthetic photometry
        self.stage("synthetic photometry", 0.16)
        self.nb = False
        if not self.offline:
            rough = self.rough_g_flux()
            Rr, _ = glow_radius(rough, lambda r, c: generic_wing_arcsec(r, self.fwhm), self.sig0,
                                geom.A_px, self.fwhm, p.maxradius * 60.0, nc)
            prov = select_casters(Rr, self.fwhm, self.frame_dist, table.g, True, p.faintG)
            need = (self.inside | prov) & (table.g <= XP_G_MAX)
            table = cat.attach_spectra(table, need)
            self.table = table
            curves, desc, nb = channel_curves(nc, self.cfg, self.spcc_root(), getattr(kw, "filter", ""), R)
            self.nb = nb
            R.info(f"Channel responses: {desc}")
            sp = SyntheticPhotometry(curves, R)
            kappa, S, colour = sp.compute(table, allow_hip=not nb)
            self.kappa, self.S, self.colour = kappa, S, colour
            self.prior_sig = sp.prior_sig
            self.alt_ratio = sp.alt_ratio
            nx = int(np.sum(colour == "xp"))
            # SPEC (round 15): route B report, or why the table stars fall back
            nh = int(np.sum(colour == "hip"))
            nhip = int(np.sum(table.hip >= 0))
            if nh:
                hr = sp.hip_rel
                R.info(f"Route B (Hipparcos V, B-V, V-I): colour relation fitted on {hr['n']} field XP "
                       f"stars (G > {HIP_REL_GMIN:.0f}), scatter " + ", ".join(f"{v:.3f}" for v in hr["mad"])
                       + f" mag per channel, B-V {hr['bv_range'][0]:+.2f} to {hr['bv_range'][1]:+.2f}; "
                       f"used for {nh} stars")
                R.number("route_b", {"n_rel": hr["n"], "mad": [float(v) for v in hr["mad"]], "n": nh})
            elif nhip:
                R.info(f"Route B unavailable ({sp.hip_note}): the {nhip} bright-table stars keep the "
                       "Gaia XP or Teff (B-V) route")
            R.info(f"Colour sources: XP {nx}, Hipparcos {nh}, Teff {int(np.sum(colour == 'teff'))}, none "
                   f"{int(np.sum(colour == 'none'))}; positions from "
                   f"{', '.join(sorted(cat.sources_used['positions']))}; spectra from "
                   f"{', '.join(sorted(cat.sources_used['spectra'])) or 'none'}")
            R.number("sources", {k: sorted(v) for k, v in cat.sources_used.items()})
        self.merge_close_stars()
        table, xs, ys = self.table, self.xs, self.ys
        kappa, S = self.kappa, self.S
        # ---- pass 0 photometry
        self.stage("photometry, pass 0", 0.20)
        self.r_ap_px = AP_FWHM * self.fwhm_px
        self.psf_file = None
        self.psf_sel = None
        if p.psf == "selection":
            self.psf_sel = self.read_psf_selection()
        elif p.psf != "measure":
            optics = self.optics()
            self.psf_file, rap = load_psf_file(p.psf, nc, self.fwhm, optics, R, ctx.soft)
            self.r_ap_px = rap / geom.scale
            R.info(f"Loaded PSF '{p.psf}' (r_ap {rap:.2f}\")")
        cand = self.calibration_candidates() if not self.offline else \
            (self.inside & geom_ok(geom, xs, ys, EDGE_FWHM * self.fwhm_px) & (self.rsat == 0))
        Fm0 = np.full((len(table), nc), np.nan)
        snr0 = np.zeros((len(table), nc))
        good0 = np.zeros((len(table), nc), bool)
        idx = np.nonzero(cand)[0]
        for c in range(nc):
            f, nap, pk = aperture_fluxes(img[c], xs[idx], ys[idx], self.r_ap_px, "annulus",
                                         fwhm_px=self.fwhm_px)
            Fm0[idx, c] = f
            snr0[idx, c] = f / (self.sig0[c] * np.sqrt(self.eta * np.maximum(nap, 1)))
            good0[idx, c] = np.isfinite(f) & (snr0[idx, c] > SNR_MIN) & (pk < self.lin[c])
        if self.offline:
            cal0 = Calibration(zp=np.zeros(nc), k=np.zeros(nc), kappa0=0.0,
                               sigma_agree=np.zeros(nc), n_stars=np.sum(good0, axis=0))
        else:
            cal0 = fit_calibration(Fm0, S, kappa, good0, snr0, R, label="pass 0")
        if np.min(cal0.n_stars) < 3 and not self.offline:
            raise HardRefusal(f"Too few calibration stars ({int(np.min(cal0.n_stars))}) to calibrate "
                              "the image against Gaia. Check that the image is linear, plate "
                              "solved and contains unsaturated stars.")
        F0 = cal0.predict(S, kappa)
        self.F0 = F0
        R.info("Pass 0 zero points " + ", ".join(f"{z:.3f}" for z in cal0.zp) +
               " (" + ", ".join(str(n) for n in cal0.n_stars) + " stars)")
        # ---- provisional selection
        self.stage("provisional star selection", 0.24)
        gen = lambda r, c: generic_wing_arcsec(r, self.fwhm)
        R0, _ = glow_radius(F0, gen, self.sig0, geom.A_px, self.fwhm, p.maxradius * 60, nc)
        R0sel, _ = glow_radius(F0, gen, self.sig0, geom.A_px, self.fwhm, p.maxradius * 60, nc, level=SELECT_SIGMA)
        cast0 = select_casters(R0sel, self.fwhm, self.frame_dist, table.g, p.auto, p.faintG)
        if not p.auto and cast0.sum() > P4_MAX_STARS:
            ctx.soft(f"-faintG={p.faintG} selects {int(cast0.sum())} stars: slow, and the faint "
                     "stars' noise is over-subtracted.")
        R.info(f"Provisional glow-casters: {int(cast0.sum())} ({int((cast0 & self.inside).sum())} in frame)")
        # ---- joint fit
        self.stage("joint background and wing fit", 0.28)
        self.joint_fit(cast0, F0, R0)
        # ---- glow^(0), sigma_bg
        self.stage("provisional glow model", 0.36)
        # SPEC: one coarse factor b' for the whole image (4, or 8 when the x4
        # grid would exceed 4 Mpx), shared by the rings and the rendering.
        bprime = 4 if (h / 4.0) * (w / 4.0) <= COARSE_MAX_PIX else 8
        self.renderer = ModelRenderer((h, w), geom, bprime, nc)
        idx0 = np.nonzero(cast0)[0]
        pf0 = make_p0_function(self.pjoint, self.rho0, self.fwhm)
        # SPEC: glow^(0) is rendered out to each caster's provisional R_glow
        # (where it falls below 0.1 sigma_bg^(0)), not to maxradius.
        st0 = [RenderStar(xs[i], ys[i], F0[i].copy(), float(R0[i]), rmin=3 * self.fwhm) for i in idx0]
        self.model0 = self.renderer.render(st0, lambda r, c: pf0(r), ctx)
        self.model0_index = {int(i): k for k, i in enumerate(idx0)}
        self.noise_levels()
        self.nebula_check()
        # ---- pass 1 photometry
        self.stage("photometry, pass 1", 0.42)
        if self.offline:
            self.good1 = good0
            cal = Calibration(zp=np.zeros(nc), k=np.zeros(nc), kappa0=0.0,
                              sigma_agree=np.zeros(nc), n_stars=np.sum(good0, axis=0))
            Fpred = F0.copy()
            R.info("Catalogue agreement, linearity slope, bright/faint overlap: not measurable "
                   "(no catalogue)")
        else:
            cal, Fpred = self.pass1(cand, cast0, R0)
        self.cal, self.Fpred = cal, Fpred
        # ---- rings, pass 1
        self.stage("radial profiles, pass 1", 0.50)
        meas = self.measure_set(cast0, R0)
        rings = self.measure_rings(meas, cast0, R0, self.model0, self.model0_index, "p1")
        # ---- ePSF
        self.stage("extended PSF", 0.62)
        if self.psf_sel is not None:
            meas_s, rings_s = self.selection_rings(meas, cast0, R0)
            psf = self.build_psf(meas_s, rings_s, cast0)
            self.check_selection_psf(psf, len(meas_s))
        else:
            psf = self.build_psf(meas, rings, cast0)
        if self.psf_file is None:
            for it in range(1, N_TEMPLATE_REFITS + 1):
                self.stage(f"background refit {it} with the measured PSF", 0.62 + 0.01 * it)
                Rg_t, _ = glow_radius(self.Fpred, psf.pfun(), self.sig_bg, geom.A_px, self.fwhm,
                                      p.maxradius * 60.0, nc)
                cast_t = select_casters(Rg_t, self.fwhm, self.frame_dist, self.table.g, p.auto, p.faintG)
                saved = ([wf for wf in self.wf], list(self.res), self.sig_bg.copy(), self.sig_sys.copy(),
                         psf, rings)
                self.refit_background_with_psf(psf, cast_t, it)
                rings_t = self.measure_rings(meas, cast0, R0, self.model0, self.model0_index, f"t{it}")
                psf_t = self.build_psf(meas, rings_t, cast0)
                # SPEC (round 3): a refit is kept only if it does not shorten the
                # measured reach by more than 30%; on a field lying wholly inside
                # one halo (a crop) the refit is ill-conditioned, so the previous
                # background and profile are restored and the loop stops.
                r_old = psf.meta.get("r_meas") or 0.0
                r_new = psf_t.meta.get("r_meas") or 0.0
                amps = np.array([wf.template_amp for wf in self.wf], float)
                bad_amp = not np.all(np.isfinite(amps) & (amps >= REFIT_AMP_RANGE[0]) & (amps <= REFIT_AMP_RANGE[1]))
                if r_new < 0.7 * r_old or bad_amp:
                    self.wf, self.res, self.sig_bg, self.sig_sys, psf, rings = saved
                    self._res_far = None
                    R.info(f"Background refit {it} reverted: reach {r_old / 60:.1f}' -> {r_new / 60:.1f}', "
                           f"template amplitude " + ", ".join(f"{a:.2f}" for a in amps) +
                           f" (accepted range {REFIT_AMP_RANGE[0]}-{REFIT_AMP_RANGE[1]})")
                    break
                psf, rings = psf_t, rings_t
        # ---- final selection, refinement
        self.stage("final star selection", 0.66)
        cast, Rg, s_i = self.select_and_refine(psf, meas, rings)
        # SPEC (round 18): glow^(0) has served the noise levels, the pass-1 and
        # refit rings and the selection PSF; nothing reads it after this point
        self.model0 = None
        self.sat_lab = None     # read by build_masks (joint fit) only
        npass = 1
        if p.passes == "2" or (p.passes == "auto" and self.overlapping(cast, Rg)):
            npass = 2
        if npass == 2:
            self.stage("radial profiles, pass 2", 0.70)
            idx1 = np.nonzero(cast)[0]
            # SPEC (round 17): the model that the pass-2 rings subtract as "other stars"
            # uses the central flux of the unrefined casters, not their lower bound: the
            # bound is a rendering rule, and a dimmed neighbour model would leave its
            # light in a refined star's rings and raise that star's s (Alnitak test: 8
            # refined casters up to +0.18%)
            s_c = self.s_central
            st1 = [RenderStar(xs[i], ys[i], s_c[i] * Fpred[i], float(Rg[i]), taper=True) for i in idx1]
            model1 = self.renderer.render(st1, psf.pfun(), ctx)
            m_index = {int(i): k for k, i in enumerate(idx1)}
            meas2 = self.measure_set(cast, Rg)
            rings2 = self.measure_rings(meas2, cast, Rg, model1, m_index, "p2")
            # SPEC (round 3): the second ring pass no longer replaces the
            # profile. Its rings subtract the other stars' model from a
            # background that has already absorbed part of their light (the
            # frame-wide pedestal of summed wings), which drove the far profile
            # low pass after pass. Pass 2 now serves the flux refinement and the
            # selection; neighbours are handled by the sector-robust rings.
            meas, rings = meas2, rings2
            cast, Rg, s_i = self.select_and_refine(psf, meas, rings)
            del model1, st1
        # SPEC (round 18): the ring label cache (pixel sets of up to 3000 stars,
        # native and coarse) is not needed by the final render; post_checks
        # measures 3 stars with keys of its own
        if getattr(self, "ring_measurer", None) is not None:
            self.ring_measurer.cache.clear()
        R.info(f"Passes used: {npass}")
        R.number("passes", npass)
        self.star_shapes = self.inner_shapes(cast, Rg, self.s_central, psf, rings)
        self.psf = psf
        self.final_cast, self.final_Rg, self.final_s = cast, Rg, s_i
        # ---- render, cap, protect
        self.stage("rendering the glow model", 0.78)
        out, glow = self.render_and_protect(psf, cast, Rg, s_i)
        if p.amount != 1.0:
            out, glow = apply_amount(out, glow, p.amount, inplace=True)
        self.stage("sanity checks", 0.92)
        self.post_checks(out, glow, cast, Rg, psf)
        res = Result(out=out, glow=glow, label=p.label())
        res.psf_json = psf_to_json(psf, p, geom.scale, self.fwhm, self.r_ap_px * geom.scale,
                                   os.path.basename(info.get("filename") or ""),
                                   [float(z) for z in cal.zp], self.optics(), self.chan_names())
        res.warnings = list(R.warnings)
        res.numbers = dict(R.numbers)
        res.summary = self.summary_lines()
        self.stage("done", 0.98)
        return res

    # -- pieces ------------------------------------------------------------
    def chan_names(self):
        return ["R", "G", "B"] if self.nc == 3 else ["L"] if self.nc == 1 else [str(c) for c in range(self.nc)]

    def spcc_root(self):
        udd = self.io.userdatadir()
        return str(Path(udd).parent / "siril-spcc-database") if udd else None

    def optics(self):
        kw = self.info["keywords"]
        d = getattr(kw, "date_obs", None)
        return {"telescop": str(getattr(kw, "telescop", "") or ""),
                "instrume": str(getattr(kw, "instrume", "") or ""),
                "focallen_mm": float(getattr(kw, "focal_length", 0) or 0),
                "filter": str(getattr(kw, "filter", "") or ""),
                "date_obs": d.isoformat() if isinstance(d, datetime) else ""}

    def merge_close_stars(self):
        """SPEC (addition): stars closer than max(2 FWHM, 4") are unresolved at
        the image scale and are merged into one caster with summed flux before
        selection and refinement. Two co-located casters (e.g. zeta Ori A and B,
        2.4" apart, both from the bright-star supplement) would otherwise each
        be fitted against the same rings and the glow subtracted about twice.
        The merged star takes the position of its brightest member when that
        member was recentred on the image (detection or saturated region),
        otherwise the flux-weighted position."""
        n = len(self.table)
        if n < 2:
            self.merged = np.zeros(n, bool)
            self.merge_members = [[i] for i in range(n)]
            return
        rad = max(MERGE_FWHM * self.fwhm_px, MERGE_ARCSEC / self.geom.scale)
        fin = np.isfinite(self.xs) & np.isfinite(self.ys)
        idx = np.nonzero(fin)[0]
        tree = cKDTree(np.column_stack([self.xs[idx], self.ys[idx]]))
        pairs = tree.query_pairs(rad, output_type="ndarray")
        self.merged = np.zeros(n, bool)
        self.merge_members = [[i] for i in range(n)]
        if pairs.size == 0:
            return
        parent = np.arange(n)

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a, b in pairs:
            ra_, rb_ = find(idx[a]), find(idx[b])
            if ra_ != rb_:
                parent[rb_] = ra_
        roots = np.array([find(i) for i in range(n)])
        groups = {}
        for i in range(n):
            groups.setdefault(roots[i], []).append(i)
        flux = np.nansum(np.where(np.isfinite(self.S), self.S, 0), axis=1)
        keep = np.ones(n, bool)
        names = self.table.name.copy()
        nmerged = 0
        examples = []
        for members in groups.values():
            if len(members) < 2:
                continue
            m = np.array(members)
            b = m[np.argmax(flux[m])]
            fw = flux[m] / max(flux[m].sum(), 1e-300)
            if not self.recentred[b]:
                self.xs[b] = float(np.sum(fw * self.xs[m]))
                self.ys[b] = float(np.sum(fw * self.ys[m]))
            self.S[b] = np.nansum(self.S[m], axis=0)
            self.kappa[b] = float(np.sum(fw * self.kappa[m]))
            self.table.g[b] = -2.5 * math.log10(max(np.sum(10 ** (-0.4 * self.table.g[m])), 1e-300))
            self.rsat[b] = float(np.max(self.rsat[m]))
            nm = [str(names[j]) for j in m[np.argsort(-flux[m])] if names[j]]
            if nm:
                names[b] = "+".join(nm)
            keep[m] = False
            keep[b] = True
            self.merged[b] = True
            self.merge_members[b] = [int(j) for j in m]
            nmerged += len(m) - 1
            if len(examples) < 3 and flux[b] >= np.percentile(flux, 99):
                examples.append(names[b] or f"G={self.table.g[b]:.2f}")
        self.table.name = names
        sub = np.nonzero(keep)[0]
        self.table = self.table.subset(sub)
        for att in ("xs", "ys", "rsat", "kappa", "S", "colour", "merged", "recentred", "prior_sig",
                    "alt_ratio"):
            setattr(self, att, getattr(self, att)[sub])
        self.merge_members = [self.merge_members[i] for i in sub]
        self.inside = self.geom.in_frame(self.xs, self.ys) & np.isfinite(self.xs)
        self.frame_dist = self.geom.frame_distance_arcsec(self.xs, self.ys) if not self.offline \
            else np.zeros(len(sub))
        self.R.info(f"Merged {nmerged} catalogue stars into close companions (unresolved within "
                    f"{rad:.1f} px)" + (f", e.g. {', '.join(examples)}" if examples else ""))

    def rough_g_flux(self):
        """G-only flux scale per channel, used only to choose which stars
        need spectra (SPEC: the spec's step 2 needs provisional casters,
        which need a flux scale that pass 0 only provides after spectra)."""
        t, nc = self.table, self.nc
        sel = self.inside & (t.g > 9) & (t.g < 15) & geom_ok(self.geom, self.xs, self.ys, 10 * self.fwhm_px)
        idx = np.nonzero(sel)[0]
        idx = idx[np.argsort(t.g[idx])][:400]
        out = np.zeros((len(t), nc))
        for c in range(nc):
            f, nap, pk = aperture_fluxes(self.img[c], self.xs[idx], self.ys[idx], AP_FWHM * self.fwhm_px,
                                         "annulus", fwhm_px=self.fwhm_px)
            ok = np.isfinite(f) & (f > 0) & (pk < self.lin[c])
            zp = np.median(f[ok] / 10 ** (-0.4 * t.g[idx][ok])) if ok.sum() >= 3 else 1e6
            out[:, c] = zp * 10 ** (-0.4 * t.g)
        return out

    def calibration_candidates(self):
        t = self.table
        g = t.g
        ok = self.inside & geom_ok(self.geom, self.xs, self.ys, EDGE_FWHM * self.fwhm_px)
        ok &= (self.colour != "none") & (g <= 16.5) & (self.rsat == 0) & (t.src != "D")
        idx = np.nonzero(ok)[0]
        if idx.size == 0:
            return ok
        # Gaia neighbours brighter than G + 2.5 within 6 FWHM
        allm = self.inside | (self.frame_dist < 10 * self.fwhm)
        tree = cKDTree(np.column_stack([self.xs[allm], self.ys[allm]]))
        gall = g[allm]
        rad = NEIGHBOUR_FWHM * self.fwhm_px
        bad = np.zeros(idx.size, bool)
        for k, i in enumerate(idx):
            nb = tree.query_ball_point([self.xs[i], self.ys[i]], rad)
            for j in nb:
                if gall[j] < g[i] + NEIGHBOUR_DMAG and abs(gall[j] - g[i]) + \
                        np.hypot(self.xs[allm][j] - self.xs[i], self.ys[allm][j] - self.ys[i]) > 1e-6:
                    bad[k] = True
                    break
        # SPEC: detection neighbours: a detection within 6 FWHM (beyond
        # 1.5 FWHM) with an amplitude >= 10% (2.5 mag) of the star's own.
        if self.alld:
            dxy = np.array([[d.x, d.y] for d in self.alld])
            dpk = np.array([d.peak if not d.saturated else np.inf for d in self.alld])
            dtree = cKDTree(dxy)
            for k, i in enumerate(idx):
                if bad[k]:
                    continue
                nb = dtree.query_ball_point([self.xs[i], self.ys[i]], rad)
                if not nb:
                    continue
                nb = np.array(nb)
                dd = np.hypot(dxy[nb, 0] - self.xs[i], dxy[nb, 1] - self.ys[i])
                own = nb[dd <= 1.5 * self.fwhm_px]
                opk = np.max(dpk[own]) if own.size else 0.0
                oth = nb[dd > 1.5 * self.fwhm_px]
                if oth.size and np.any(dpk[oth] >= 10 ** (-0.4 * NEIGHBOUR_DMAG) * max(opk, 1e-12)):
                    bad[k] = True
        ok[idx[bad]] = False
        return ok

    def build_masks(self, casters, F0):
        """Mask for the joint fit and the core list for the rings (spec 6, 8.2)."""
        img, geom = self.img, self.geom
        h, w = self.h, self.w
        valid = np.all(np.isfinite(img) & (img != 0), axis=0)
        if getattr(self, "fill", None) is not None:
            valid &= ~self.fill
        for c in range(self.nc):
            valid &= img[c] < self.lin[c]
        self.ring_valid = valid.copy()
        self.sat_native = np.zeros((h, w), bool)
        for c in range(self.nc):
            self.sat_native |= img[c] >= self.lin[c]
        cx, cy, cr = [], [], []
        areas = np.bincount(self.sat_lab.ravel())
        for d in self.alld:
            r = CORE_MASK_FWHM * (d.fwhm if d.fwhm > 0 else self.fwhm_px)
            if d.saturated:
                L = self.sat_lab[min(h - 1, max(0, int(round(d.y)))), min(w - 1, max(0, int(round(d.x))))]
                if L > 0:
                    r = math.sqrt(areas[L] / math.pi) + CORE_MASK_FWHM * self.fwhm_px
            cx.append(d.x)
            cy.append(d.y)
            cr.append(r)
        t = self.table
        # SPEC: Gaia neighbour cores are masked for in-frame stars with
        # G <= 14 (radius saturated disc + 3 FWHM); fainter ones rely on the
        # detections, otherwise a Milky Way field would be masked entirely.
        sel = self.inside & (t.g <= G_NEIGHBOUR_MASK)
        for i in np.nonzero(sel)[0]:
            cx.append(self.xs[i])
            cy.append(self.ys[i])
            cr.append(self.rsat[i] + CORE_MASK_FWHM * self.fwhm_px)
        self.cores = (np.array(cx), np.array(cy), np.array(cr))
        self.core_tree = cKDTree(np.column_stack([self.cores[0], self.cores[1]])) if cx else None
        cores = np.zeros((h, w), bool)
        paint_circles(cores, *self.cores)
        jmask = valid & ~cores
        # inner zones of strong casters
        gen0 = generic_wing_arcsec(np.array([self.rho0]), self.fwhm)[0] * geom.A_px
        strong = casters & np.any(F0 * gen0 > INNER_MASK_SIGMA * self.sig0[None, :], axis=1) & \
            (self.frame_dist < self.rho0)
        inner = np.zeros((h, w), bool)
        idx = np.nonzero(strong)[0]
        paint_ellipses(inner, geom, self.xs[idx], self.ys[idx], np.full(idx.size, self.rho0))
        jmask &= ~inner
        self.inner_zone = inner
        self.inner_casters = strong
        self.core_mask = cores
        return jmask

    def joint_fit(self, casters, F0, R0):
        p, R, geom = self.p, self.R, self.geom
        h, w, nc = self.h, self.w, self.nc
        b = int(math.ceil(max(h, w) / BLOCK_TARGET))
        self.b = b
        self.rho0 = max(3 * b * geom.scale, 8 * self.fwhm)
        jmask = self.build_masks(casters, F0)
        self.jmask = jmask
        jb = JointBackground((h, w), geom, b, self.rho0, p.maxradius * 60.0, p.bgorder, R)
        self.jb = jb
        idx = np.nonzero(casters)[0]
        xy = list(zip(self.xs[idx], self.ys[idx]))
        Fcols = np.column_stack([F0[idx], F0[idx].sum(axis=1)]) if nc > 1 else F0[idx]
        pfile = None
        if self.psf_file is not None:
            pfile = lambda r: self.psf_file.eval(r, -1)
        D = jb.annulus_images(xy, Fcols, jmask, pfun=pfile)
        self.wf = []
        self.block_y = []
        for c in range(nc):
            self.ctx.check_cancel()
            y = jb.block_data(self.img[c], jmask)
            self.block_y.append(y)
            self.wf.append(jb.fit(y, D[c], template=pfile is not None))
        if nc > 1:
            lum = np.sum(self.img, axis=0)
            y = jb.block_data(lum, jmask)
            del lum
            self.block_y.append(y)
            self.wf_L = jb.fit(y, D[nc], template=pfile is not None)
        else:
            self.wf_L = self.wf[0]
        wl = self.wf_L
        if pfile is not None:
            R.info(f"Background: order {p.bgorder}, residual RMS {wl.rms:.3g}, PSF-file template "
                   f"amplitude {wl.template_amp:.3f} (expected about 1)")
            self.pjoint = None
        else:
            R.info(f"Background: order {p.bgorder}, residual RMS {wl.rms:.3g}, wing bases kept "
                   f"{wl.n_kept} of {jb.K}, effective dof {wl.dof_wing:.2f}, block {b} px, rho0 "
                   f"{self.rho0:.0f}\"")
            if not wl.usable:
                R.warn("The background/wing fit is degenerate (fewer than 2 identifiable wing bases, "
                       "or all with > 50% error): the joint-fit wing is not used.")
            self.pjoint = jb.p_joint_function(wl) if wl.usable else None
        R.number("background", {"order": p.bgorder, "rms": wl.rms, "kept": wl.n_kept,
                                "dof": wl.dof_wing})
        self.res = [jb.residual_map(wf) for wf in self.wf]
        self.wf_bases = list(self.wf)
        self.res_bases = list(self.res)

    def refit_background_with_psf(self, psf, cast, it):
        """SPEC (round 3): refit the joint background with the measured ePSF
        (luminance shape, per unit calibrated flux) as a single non-negative
        wing template, as the spec's -psf path does. The tilted annular bases
        cannot represent wings shallower than r^-alpha0, so the polynomial
        absorbed broad shallow wings and every ring beyond ~2' came out low;
        refitting with the measured shape lets that light be claimed back,
        and the rings are then re-measured against the new background. The
        joint-fit wing from the bases (wf_L) is kept for the tail and the
        level check."""
        nc = self.nc
        idx = np.nonzero(cast)[0]
        if idx.size == 0:
            return
        xy = list(zip(self.xs[idx], self.ys[idx]))
        Fp = self.Fpred[idx]
        Fcols = np.column_stack([Fp, Fp.sum(axis=1)]) if nc > 1 else Fp
        D = self.jb.annulus_images(xy, Fcols, self.jmask, pfun=lambda r: psf.eval(r, -1))
        amps = []
        for c in range(nc):
            self.ctx.check_cancel()
            self.wf[c] = self.jb.fit(self.block_y[c], D[c], template=True)
            amps.append(self.wf[c].template_amp)
        self.res = [self.jb.residual_map(wf) for wf in self.wf]
        self._res_far = None
        self.noise_levels()
        self.R.info(f"Background refit {it} with the measured ePSF as wing template: amplitude "
                    + ", ".join(f"{a:.2f}" for a in amps) + " (1 = profile consistent with the "
                    "large-scale light)")
        self.R.number(f"template_amp_{it}", amps)

    def bg_rows(self, c, y0, y1):
        return eval_poly_image(self.wf[c].poly, self.p.bgorder, self.h, self.w, y0, y1)

    def bg_full(self, c):
        """SPEC (round 18): the full-frame background of channel c, cached per
        channel for its current polynomial (it was evaluated ~9 times per
        channel). The array is read-only: callers make their own copies."""
        poly = np.asarray(self.wf[c].poly, float)
        key = (int(self.p.bgorder), poly.tobytes())
        cache = self.__dict__.setdefault("_bg_cache", {})
        hit = cache.get(c)
        if hit is not None and hit[0] == key:
            return hit[1]
        cache.pop(c, None)
        # the final per-channel loop keeps only the current channel (memory peak)
        if len(cache) >= getattr(self, "_bg_cache_limit", self.nc):
            cache.clear()
        bg = eval_poly_image(poly, self.p.bgorder, self.h, self.w)
        bg.flags.writeable = False
        cache[c] = (key, bg)
        return bg

    def res_at(self, c, X, Y):
        b = self.b
        return ndimage.map_coordinates(self.res[c], [(Y + 0.5) / b - 0.5, (X + 0.5) / b - 0.5],
                                       order=1, mode="nearest")

    def noise_levels(self):
        """sigma_bg,c and sigma_bg,sys,c (spec 6)."""
        jb = self.jb
        valid_blocks = np.isfinite(self.wf_L.residual.reshape(jb.nby, jb.nbx))
        bvalid = np.repeat(np.repeat(valid_blocks, jb.b, 0), jb.b, 1)[:self.h, :self.w]
        sig, sys_ = [], []
        lag_sig = []
        for c in range(self.nc):
            vals = []
            lags = []
            L_ = NOISE_LAG_PX
            for y0 in range(0, self.h, 512):
                y1 = min(self.h, y0 + 512)
                rr = slice(0, y1 - y0, 4)
                v = (self.img[c][y0:y1] - self.bg_rows(c, y0, y1) - self.model0.native_rows(c, y0, y1))[rr]
                m = (self.jmask[y0:y1] & bvalid[y0:y1])[rr]
                vals.append(v[m])
                # SPEC (round 20): pixel differences at a lag of NOISE_LAG_PX along the rows
                mm = m[:, L_:] & m[:, :-L_]
                lags.append((v[:, L_:] - v[:, :-L_])[mm])
            v = np.concatenate(vals) if vals else np.zeros(0)
            s_res = mad_sigma(v) if v.size > 100 else float(self.sig0[c])
            # SPEC (round 20): sigma_bg is the background's pixel noise. The MAD of the
            # residual also holds whatever the background polynomial leaves of large
            # structure: on M31 the galaxy doubled it (4.7e-6 against 2.3e-6 pixel
            # noise), and on a 2414 x 1687 crop next to the galaxy (the user's GUI
            # run) it came out 6x too high (1.44e-5). The clamp's noise allowances,
            # the safety net and every sigma-gated rule scale with it: the clamp then
            # let the model through 1e-5 below the sky, as dark lanes. Differences of
            # pixels NOISE_LAG_PX apart (beyond the stack's interpolation kernel)
            # measure the noise without the structure; the residual's MAD is kept
            # where it is at most NOISE_LAG_CAP times that (bubble 1.00-1.03,
            # Alnitak 1.13, so those frames are unchanged).
            dv = np.concatenate(lags) if lags else np.zeros(0)
            s_lag = mad_sigma(dv) / math.sqrt(2.0) if dv.size > 100 else s_res
            lag_sig.append(s_lag)
            sig.append(min(s_res, NOISE_LAG_CAP * s_lag) if s_lag > 0 else s_res)
            # SPEC (round 3): sigma_bg,sys is measured on blocks where the
            # provisional glow is negligible (< 0.05 sigma). Over all blocks it
            # also contains the glow the joint fit cannot represent (wings
            # shallower than r^-alpha0), which inflated every far ring's error
            # and cut the measured reach short.
            jb_ = self.jb
            cm = self.model0.coarse[c]
            yc = np.clip(((np.arange(jb_.nby) + 0.5) * jb_.b / self.renderer.b).astype(int), 0, cm.shape[0] - 1)
            xc = np.clip(((np.arange(jb_.nbx) + 0.5) * jb_.b / self.renderer.b).astype(int), 0, cm.shape[1] - 1)
            quiet = valid_blocks & (cm[np.ix_(yc, xc)] < 0.05 * sig[-1])
            if quiet.sum() >= 50:
                rmap = self.res[c][quiet]
                sys_.append(mad_sigma(rmap))   # robust: unmodelled structure (e.g. a galaxy) must not inflate it
            else:
                # glow everywhere (e.g. a crop around one bright star): use the
                # block-to-block scatter of a high-pass of the residual, which
                # measures small-scale background systematics, not the glow
                hp = self.res[c] - ndimage.gaussian_filter(self.res[c], 3.0, mode="nearest")
                sys_.append(1.4826 * float(np.median(np.abs(hp[valid_blocks]))) if valid_blocks.any() else 0.0)
        self.sig_bg = np.array(sig)
        self.sig_sys = np.array(sys_)
        self.R.info("Noise sigma_bg " + ", ".join(f"{s_:.3g}" for s_ in self.sig_bg) +
                    "; sigma_bg,sys " + ", ".join(f"{s_:.3g}" for s_ in self.sig_sys) +
                    " (pixel-difference noise " + ", ".join(f"{s_:.3g}" for s_ in lag_sig) + ")")

    # -- PSF from a selection (SPEC round 5) --------------------------------
    def read_psf_selection(self):
        sel = getattr(self, "user_sel", None)
        if sel is None:
            raise HardRefusal("-psf=selection: no selection in Siril. Draw a rectangle on a "
                              "nebula-free part of the image (with bright stars in it) and run again.")
        x, y, w_, h_ = sel
        h, w = self.h, self.w
        x0, x1 = max(0, x), min(w, x + w_)
        # display rows (y from the top) -> FITS rows
        y0, y1 = max(0, h - (y + h_)), min(h, h - y)
        if x1 - x0 < 20 or y1 - y0 < 20:
            raise HardRefusal(f"-psf=selection: the selection ({w_} x {h_} px) is too small or outside "
                              "the image.")
        self.R.info(f"PSF from selection: x {x0}-{x1}, y {y0}-{y1} (FITS rows), {x1 - x0} x {y1 - y0} px")
        return (x0, x1, y0, y1)

    def selection_mask(self):
        """Pixels whose ring samples may enter the PSF: the selection, plus the
        joint-fit background blocks judged clean (|residual| <= 3 MAD)."""
        h, w = self.h, self.w
        x0, x1, y0, y1 = self.psf_sel
        m = np.zeros((h, w), bool)
        m[y0:y1, x0:x1] = True
        jb = self.jb
        try:
            res = np.asarray(self.wf_L.residual, float).reshape(jb.nby, jb.nbx)
            fin = np.isfinite(res)
            if fin.sum() >= 50:
                med = float(np.median(res[fin]))
                sc = mad_sigma(res[fin])
                clean = fin & (np.abs(res - med) <= I18_RES_SIGMA * sc)
                up = np.repeat(np.repeat(clean, jb.b, axis=0), jb.b, axis=1)[:h, :w]
                m |= up
                self.R.info(f"PSF from selection: ring samples from the selection and "
                            f"{100 * clean.mean():.0f}% of the background blocks judged clean")
        except Exception:
            pass
        return m

    def selection_rings(self, meas, casters, Rg):
        x0, x1, y0, y1 = self.psf_sel
        xs, ys = self.xs[meas], self.ys[meas]
        inr = (xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1)
        ms = meas[inr]
        if ms.size < SEL_MIN_STARS:
            raise HardRefusal(f"-psf=selection: only {ms.size} usable stars have their centres in the "
                              f"selection (at least {SEL_MIN_STARS} needed). Enlarge the selection, "
                              "or use a PSF file measured on a clean field.")
        mask = self.selection_mask()
        saved_rv, saved_rm = self.ring_valid, getattr(self, "ring_measurer", None)
        try:
            self.ring_valid = saved_rv & mask
            self.ring_measurer = None          # its cache holds the full-image pixel sets
            rings = self.measure_rings(ms, casters, Rg, self.model0, self.model0_index, "sel")
        finally:
            self.ring_valid, self.ring_measurer = saved_rv, saved_rm
        g = self.table.g[ms]
        self.R.info(f"PSF from selection: {ms.size} stars with centres in the selection "
                    f"(brightest G = {np.min(g):.1f})")
        return ms, rings

    def check_selection_psf(self, psf, n):
        fw = self.fwhm
        rm = float(psf.meta.get("r_meas") or 0.0)
        if rm < SEL_MIN_REACH_FWHM * fw:
            raise HardRefusal(f"-psf=selection: the profile could only be measured to {rm:.0f}\" "
                              f"({rm / fw:.1f} FWHM; at least {SEL_MIN_REACH_FWHM:.0f} needed). The "
                              "selection needs brighter stars: enlarge it, or use a clean-field PSF file.")
        msg = (f"PSF from selection: measured to {rm / 60:.1f}' ({rm / fw:.0f} FWHM) from {n} stars; "
               "beyond that the wing is the lower of the joint-fit wing and a power law from the "
               "last measured rings (errs low)")
        if rm < SEL_WARN_REACH_FWHM * fw:
            self.R.warn(msg + ". The reach is short: the far glow may be under-corrected.")
        else:
            self.R.info(msg)
        psf.meta["source"] = "selection"

    def nebula_check(self):
        """I18: SPEC: the spec's |res| > 3 sigma_bg,sys test (sigma_bg,sys being
        the RMS of res) can never reach 25%; the robust MAD scale is used."""
        r = self.wf_L.residual
        r = r[np.isfinite(r)]
        if r.size < 50:
            return
        sc = mad_sigma(r)
        frac = float(np.mean(np.abs(r - np.median(r)) > I18_RES_SIGMA * sc)) if sc > 0 else 0.0
        self.R.number("nebula_fraction", frac)
        if frac > I18_FRACTION:
            self.R.warn(f"{100 * frac:.0f}% of the background blocks deviate strongly from the fit: "
                        "this looks like a nebula-dominated field, and a PSF measured here can take "
                        "nebulosity for glow. Use a clean-field PSF: load one saved from a nebula-free "
                        "field taken with the same optics (-psf=<file>; GUI: PSF 'file'), or draw a "
                        "rectangle on a nebula-free part of this image and use -psf=selection.")

    def pass1(self, cand, cast0, R0):
        p, R, ctx = self.p, self.R, self.ctx
        nc = self.nc
        t = self.table
        cand = cand & ~self.inner_zone_star()
        idx = np.nonzero(cand)[0]
        Fm = np.full((len(t), nc), np.nan)
        snr = np.zeros((len(t), nc))
        good = np.zeros((len(t), nc), bool)
        for c in range(nc):
            ctx.check_cancel()
            base = self.bg_full(c) + self.model0.native(c)

            def sky(y0, y1, x0, x1, c=c, base=base):
                Y, X = np.mgrid[y0:y1, x0:x1]
                return base[y0:y1, x0:x1] + self.res_at(c, X, Y)
            f, nap, pk = aperture_fluxes(self.img[c], self.xs[idx], self.ys[idx], self.r_ap_px, "sky",
                                         sky_fn=sky)
            Fm[idx, c] = f
            snr[idx, c] = f / (self.sig_bg[c] * np.sqrt(self.eta * np.maximum(nap, 1)))
            good[idx, c] = np.isfinite(f) & (snr[idx, c] > SNR_MIN) & (pk < self.lin[c])
            del base
        cal = fit_calibration(Fm, self.S, self.kappa, good, snr, R, with_slope=True)
        self.good1 = good
        self.Fmeas1 = Fm
        names = self.chan_names()
        for c in range(nc):
            R.info(f"Catalogue agreement {names[c]}: sigma_agree = {cal.sigma_agree[c]:.3f} mag on "
                   f"{cal.n_stars[c]} stars (ZP {cal.zp[c]:.3f}, colour term {cal.k[c]:+.3f})")
        R.number("sigma_agree", [float(v) for v in cal.sigma_agree])
        R.number("n_cal", [int(v) for v in cal.n_stars])
        if np.min(cal.n_stars) < MIN_CAL_STARS:
            raise HardRefusal(f"Only {int(np.min(cal.n_stars))} calibration stars (at least "
                              f"{MIN_CAL_STARS} needed). Likely causes: non-linear data, a wrong "
                              "solution, heavy nebulosity, or too few unsaturated stars.")
        worst = float(np.nanmax(cal.sigma_agree))
        if not np.isfinite(worst) or worst > SIGMA_AGREE_ABORT:
            raise HardRefusal(f"The image does not agree with Gaia (sigma_agree {worst:.2f} mag > "
                              f"{SIGMA_AGREE_ABORT}): the flux predictions would be wrong by 40% or "
                              "more. Likely causes: non-linear data, a wrong solution, heavy "
                              "nebulosity, or no flat-field (vignetting)."
                              + (" Narrowband data: the XP spectra are smoothed at the line, see "
                                 "the help." if self.nb else ""))
        if worst > SIGMA_AGREE_WARN:
            R.warn(f"Catalogue agreement is poor (sigma_agree {worst:.2f} mag > {SIGMA_AGREE_WARN}).")
        # I4 linearity slope
        if np.isfinite(cal.beta):
            R.info(f"Linearity slope beta = {cal.beta:.3f} +- {cal.beta_err:.3f}")
            R.number("beta", cal.beta)
            if not (I4_SOFT[0] <= cal.beta <= I4_SOFT[1]):
                self.ctx.soft(f"The image looks stretched or non-linear (instrumental magnitudes "
                              f"against Gaia have slope {cal.beta:.2f}). Glow subtraction needs "
                              "linear data. Run it before any stretch.")
            elif not (I4_WARN[0] <= cal.beta <= I4_WARN[1]):
                R.warn(f"Linearity slope {cal.beta:.3f} is outside 0.95-1.05: check the data are linear.")
        else:
            R.info(f"Linearity slope: {cal.beta_note}")
            R.number("beta", None)
        Fpred = cal.predict(self.S, self.kappa)
        return cal, Fpred

    def inner_zone_star(self):
        h, w = self.h, self.w
        xi = np.clip(np.round(self.xs), 0, w - 1).astype(np.int64)
        yi = np.clip(np.round(self.ys), 0, h - 1).astype(np.int64)
        fin = np.isfinite(self.xs) & np.isfinite(self.ys)
        out = np.zeros(len(self.table), bool)
        out[fin] = self.inner_zone[yi[fin], xi[fin]] & self.inside[fin]
        return out

    def measure_set(self, casters, Rg):
        """Stars measured: calibration stars plus in-frame casters, <= 3000 by flux."""
        cal = np.any(self.good1, axis=1)
        sel = (cal | casters) & self.inside
        idx = np.nonzero(sel)[0]
        FL = np.sum(self.Fpred[idx], axis=1)
        idx = idx[np.argsort(-FL)][:MAX_RING_STARS]
        return idx

    def valid_native_fn(self):
        rv = self.ring_valid
        cx, cy, cr = self.cores
        tree = self.core_tree
        rmax = float(np.max(cr)) if cr.size else 0.0
        fwhm = self.fwhm_px

        def f(y0, y1, x0, x1, x, y):
            v = rv[y0:y1, x0:x1].copy()
            m = np.zeros(v.shape, bool)
            if tree is None:
                return v, m
            half = max(x1 - x0, y1 - y0) * 0.75 + rmax
            nb = tree.query_ball_point([x, y], half)
            if nb:
                nb = np.array(nb)
                far = np.hypot(cx[nb] - x, cy[nb] - y) > 1.5 * fwhm
                nb = nb[far]
                paint_circles(m, cx[nb] - x0, cy[nb] - y0, cr[nb])
                v &= ~m
            return v, m
        return f

    def measure_rings(self, idx, casters, Rg, model, m_index, tag):
        """Two-resolution ring medians (spec 8.2) for the stars idx."""
        p, geom, ctx = self.p, self.geom, self.ctx
        nc = self.nc
        self.rg = RingGeometry(geom, self.fwhm, p.maxradius * 60.0)
        rm = getattr(self, "ring_measurer", None)
        if rm is None or rm.rg.n != self.rg.n:
            rm = RingMeasurer((self.h, self.w), geom, self.rg, nc, self.renderer.b, self.eta, self.R)
            self.ring_measurer = rm
        rm.rg = self.rg
        rm.sig_bg = np.asarray(self.sig_bg, float)
        b = self.renderer.b
        work = []
        workc = []
        mmean = np.zeros((self.h, self.w), np.float32)
        cvalid = None
        for c in range(nc):
            ctx.check_cancel()
            mod = model.native(c)
            mmean += mod / nc
            wk = self.img[c] - self.bg_full(c) - mod
            del mod
            work.append(wk)
        # SPEC: the coarse rings use one global block median of the work image
        # (img - bg - total model) and add the star's own model back at the cell
        # centre, instead of a per-star block median of (work + own); the own
        # model varies little across a b' x b' cell beyond 50 px.
        valid_c = self.ring_valid & ~self.core_mask
        for c in range(nc):
            med, frac = masked_block_median(work[c], valid_c, b)
            workc.append(med)
        cvalid = np.isfinite(workc[0])
        satc = np.nanmean(block_view((self.sat_native & ~self.core_mask).astype(np.float32), b), axis=2)
        satc = np.nan_to_num(satc[:workc[0].shape[0], :workc[0].shape[1]])
        mcoarse = np.mean(model.coarse, axis=0)
        vfn = self.valid_native_fn()
        rings = {}
        lim = 50 * geom.scale
        # SPEC (round 11): the ring loop reports a real fraction inside its stage's
        # span of the overall progress (stage() values), instead of a pulse
        span = {"p1": (0.50, 0.62), "p2": (0.70, 0.78), "sel": (0.62, 0.66)}.get(tag, (0.62, 0.66))
        for n_i, i in enumerate(idx):
            if n_i % 25 == 0:
                ctx.check_cancel()
                ctx.progress(f"GaiaGlowSubtraction: rings {n_i}/{len(idx)}",
                             span[0] + (span[1] - span[0]) * n_i / max(1, len(idx)))
            x, y = self.xs[i], self.ys[i]
            if casters[i]:
                r_out = min(p.maxradius * 60.0, 2 * Rg[i])
            else:
                r_out = min(p.maxradius * 60.0, lim)
            k = m_index.get(int(i))
            if k is not None:
                own_n = lambda X, Y, k=k: model.own_all(k, X, Y)
            else:
                own_n = lambda X, Y: np.zeros((nc,) + np.shape(X), np.float32)
            rings[int(i)] = rm.measure(int(i), x, y, r_out, work, workc, own_n, own_n,
                                       mmean, mcoarse, vfn, self.sat_native, cvalid, satc)
        # overlap check between the two resolutions (10 brightest casters).
        # SPEC: expressed in units of the combined sigma_stat of the two rings
        # (sigma_tot needs sigma_agree and F_pred, which are per-star scalings).
        cidx = [i for i in idx if casters[i]][:10]
        offs = []
        for i in cidx:
            k = m_index.get(int(i))
            own_n = (lambda X, Y, k=k: model.own_all(k, X, Y)) if k is not None \
                else (lambda X, Y: np.zeros((nc,) + np.shape(X), np.float32))
            r60 = 60 * geom.scale
            a = rm.measure(("ovn", int(i)), self.xs[i], self.ys[i], r60, work, workc, own_n, own_n,
                           None, None, vfn, self.sat_native, cvalid, satc, native_limit_px=60, force="native")
            bb = rm.measure(("ovc", int(i)), self.xs[i], self.ys[i], r60, work, workc, own_n, own_n,
                            None, None, vfn, self.sat_native, cvalid, satc, force="coarse")
            sel = (self.rg.mid >= 40 * geom.scale) & (self.rg.mid <= 60 * geom.scale) & a.ok & bb.ok
            if sel.any():
                # SPEC (round 19): the central values: the azimuthal floor resolves
                # narrower lanes on native pixels than on 4 x 4 cells by design
                d = np.sum(a.med_c[:, sel], axis=0) - np.sum(bb.med_c[:, sel], axis=0)
                s2 = np.sum(a.sig[:, sel] ** 2, axis=0) + np.sum(bb.sig[:, sel] ** 2, axis=0)
                offs.extend(list(d / np.sqrt(np.maximum(s2, 1e-30))))
        if offs:
            mo = float(np.median(offs))
            self.R.info(f"Two-resolution ring offset ({tag}): {mo:+.2f} sigma")
            self.R.number("ring_offset", mo)
            if abs(mo) > 1:
                self.R.warn(f"The full-resolution and block-median rings differ by {mo:+.2f} sigma "
                            "at 40-60 px.")
        del work, workc, mmean
        return rings

    def build_psf(self, idx, rings, casters):
        if self.psf_file is not None:
            return self.psf_file
        p, R, geom = self.p, self.R, self.geom
        rl = [rings[int(i)] for i in idx]
        Fp = self.Fpred[idx]
        satf = self.rsat[idx] > 0
        cidx = np.nonzero(casters)[0]
        F0L, FpL = np.sum(self.F0[cidx], axis=1), np.sum(self.Fpred[cidx], axis=1)
        ok = (F0L > 0) & (FpL > 0)
        level = weighted_median(F0L[ok] / FpL[ok], FpL[ok]) if ok.any() else 1.0
        b = ExtendedPSFBuilder(self.rg, geom.A_px, self.fwhm, p.maxradius * 60.0, self.nc, R)
        psf, info = b.build(rl, Fp, satf, self.cal.sigma_agree, self.sig_sys, self.wf_L if self.pjoint else None,
                            level)
        ov = info["overlap_ratio"]
        R.info(f"Bright/faint overlap ratio: {ov:.3f}" if np.isfinite(ov) else
               "Bright/faint overlap ratio: not measurable")
        R.number("overlap_ratio", ov)
        if np.isfinite(ov) and not (OVERLAP_WARN[0] <= ov <= OVERLAP_WARN[1]):
            R.warn(f"The saturated and unsaturated stars' profiles differ (ratio {ov:.2f}): Gaia's "
                   "bright-star flux scale, non-linearity or a bad saturation level.")
        jo = info.get("joint_offset")
        if jo:
            R.info(f"p_joint level check: offset {jo[0]:+.3f} +- {jo[1]:.3f} in ln p")
            R.number("joint_offset", jo)
            # SPEC: the offset is ln(p_measured / p_joint). Background extraction
            # removes large-scale glow, so it makes p_joint *weaker* than the
            # rings, i.e. a positive offset here; the spec's "< -3 sigma" is read
            # as "joint-fit wing weaker by more than 3 sigma".
            weak = jo[0] > max(I5_SIGMA * jo[1], I5_MIN_LOG_OFFSET)
            if self.hist_bgx and weak:
                self.ctx.soft("Background extraction was applied before this tool (HISTORY) and the "
                              "outer glow is weaker than the measured wing predicts: the full model "
                              "would over-subtract. Run this tool before background extraction.")
            elif weak:
                R.warn("The outer wing in the background fit is much weaker than the ring "
                       "measurement predicts: background extraction may already have been applied.")
        R.info(f"Profile safety rule: {info.get('profile_safety', PROFILE_SAFETY)}")
        R.info(f"PSF measured to {info['r_meas'] / 60:.1f}', joint fit to {info['r_joint'] / 60:.1f}', "
               f"extrapolated to {p.maxradius:.0f}' (alpha {info['alpha']:.2f})")
        R.number("reach", {"measured": info["r_meas"] / 60, "joint": info["r_joint"] / 60,
                           "alpha": info["alpha"]})
        return psf

    def select_and_refine(self, psf, idx_meas, rings):
        p, R, geom = self.p, self.R, self.geom
        t = self.table
        Rg, capped = glow_radius(self.Fpred, psf.pfun(), self.sig_bg, geom.A_px, self.fwhm,
                                 p.maxradius * 60.0, self.nc)
        # SPEC (round 3): selection uses the spec's 0.1 sigma radius (> 4 FWHM),
        # modelling the 0.02 sigma radius; with 0.02 sigma for both, nearly
        # every star became a caster (18,000 on the M31 frame: 7.5 min, 5.8 GB)
        Rsel, _ = glow_radius(self.Fpred, psf.pfun(), self.sig_bg, geom.A_px, self.fwhm,
                              p.maxradius * 60.0, self.nc, level=SELECT_SIGMA)
        cast = select_casters(Rsel, self.fwhm, self.frame_dist, t.g, p.auto, p.faintG)
        if not p.auto:
            Rg = np.maximum(Rg, SELECT_FWHM * self.fwhm)
        ncap = int((cast & capped).sum())
        if ncap:
            R.info(f"{ncap} stars have R_glow capped at -maxradius {p.maxradius:.0f}'")
        if not p.auto and cast.sum() > P4_MAX_STARS:
            self.ctx.soft(f"-faintG={p.faintG} selects {int(cast.sum())} stars.")
        # SPEC (round 15): s_i is per channel, (n, nc); only route-B stars use the channels
        s_i = np.ones((len(t), self.nc))
        held = 0
        nref = 0
        nweak = 0
        hip_lines = []
        refined = np.zeros(len(t), bool)    # SPEC (round 17)
        for i in np.nonzero(cast & self.inside)[0]:
            r_lo = max(4 * self.fwhm, (self.rsat[i] + 2 * self.fwhm_px) * geom.scale)
            args = (rings.get(int(i)), self.Fpred[i], psf, geom.A_px, self.rg, r_lo, Rg[i],
                    self.cal.sigma_agree, self.sig_sys)
            if self.colour[i] == "hip" and np.all(np.isfinite(self.prior_sig[i])):
                # SPEC (round 15): honest prior for route-B stars. The rings may brighten
                # the flux by at most HIP_PRIOR_K sigma_prior (never more than -tolerance),
                # per channel, instead of the fixed tolerance; dimming keeps REFINE_DIM_MAX,
                # since following the rings down can only under-correct. Per channel,
                # because a bright star's wing need not have its catalogue colour: against
                # the 1.1.3 profile, zeta Ori's wing on Alnitak was redder than its Hipparcos
                # colours predict (nebula, background extraction), and one luminance scale
                # would then put more model than light into the blue channel.
                w_c = np.clip(HIP_PRIOR_K * self.prior_sig[i], HIP_PRIOR_MIN, p.tolerance)
                w_l = float(np.sum(self.Fpred[i] * w_c) / max(float(np.sum(self.Fpred[i])), 1e-300))
                sv, nr, hld = refine_flux(*args, w_l)
                s_i[i] = sv
                if nr >= 5:
                    for c in range(self.nc):
                        sc, nrc, hc = refine_flux(*args, float(w_c[c]), chans=[c])
                        if nrc >= 5:
                            s_i[i, c] = sc
                            hld = hld or hc
                hip_lines.append(f"{t.name[i] or 'HIP %d' % t.hip[i]} (V {t.vmag[i]:.2f}): prior +"
                                 + "/".join(f"{v:.2f}" for v in w_c) + " mag, s "
                                 + "/".join(f"{v:.3f}" for v in s_i[i]))
            else:
                sv, nr, hld = refine_flux(*args, p.tolerance)
                s_i[i] = sv
            held += hld
            nref += nr >= 5
            nweak += nr < 0
            refined[i] = nr >= 5
        # SPEC (round 17): casters the rings could not refine get the lower bound, if
        # nothing else checks their flux either: saturated, off-frame or route-B stars.
        # An unsaturated in-frame caster is one of the stars the calibration itself is
        # fitted on (aperture photometry, sigma_agree), and the summed glow of
        # thousands of faint casters averages their errors; bounding those too took
        # 8.8% off the total model on M31 (6151 of 6255 casters) for no single-star gain.
        unref = cast & ~refined & ((self.rsat > 0) | ~self.inside | (self.colour == "hip"))
        self.s_central = s_i.copy()
        if np.any(unref):
            iu = np.nonzero(unref)[0]
            s_i[iu] = self.unrefined_bound(iu)
            FLu = np.sum(self.Fpred[iu], axis=1)
            FLall = float(np.sum(self.Fpred[cast]))
            dF = float(np.sum(FLu - np.sum(s_i[iu] * self.Fpred[iu], axis=1)))
            R.info(f"Unrefined casters at their lower-bound flux: {iu.size} ({int((unref & ~self.inside).sum())} "
                   f"off frame), median factor {np.median(np.sum(s_i[iu] * self.Fpred[iu], axis=1) / FLu):.3f}; "
                   f"cast flux -{100 * dF / max(FLall, 1e-300):.2f}%")
            R.number("unrefined", {"n": int(iu.size), "off_frame": int((unref & ~self.inside).sum()),
                                   "flux_fraction_removed": dF / max(FLall, 1e-300)})
        R.info(f"Glow-casters: {int(cast.sum())} ({int((cast & self.inside).sum())} in frame, "
               f"{int((cast & ~self.inside).sum())} off frame, {int((cast & (t.src == 'D')).sum())} "
               f"bright-table stars missing from Gaia); flux refined for {nref}; held at tolerance: {held}; "
               f"too little ring signal (s = 1): {nweak}")
        for ln in hip_lines[:5]:
            R.info("Route-B flux refinement: " + ln)
        R.number("stars", {"in_frame": int((cast & self.inside).sum()),
                           "off_frame": int((cast & ~self.inside).sum()),
                           "D": int((cast & (t.src == "D")).sum()), "held": int(held)})
        return cast, Rg, s_i

    def inner_shapes(self, cast, Rg, s_c, psf, rings):
        """SPEC (round 20): in the inner region, where the optics put lanes and spikes
        on the ring pattern, each caster's model follows its own ring floor (the dark
        lanes) brought to the local background, so that after the subtraction the
        floor sits at the background and the bright lanes are left as optics. The
        shared profile scaled by the star's flux was 5-9% above the floor of the
        M31 G = 4.5 star at 12-21 px (its shape comes from many stars), and the
        clamp then held it on a smoothed light map, leaving dark lanes.
        Per star and channel, on its rings: target_k = floor_k - P, floor_k the
        noise-corrected azimuthal floor (StarRings.flo), P the star's local sky
        offset from the background model (median of med_c - own model over the
        rings in [r1, 2 r1], r1 where its own model falls to GUARD_END_SIGMA; at
        least 0); factor_k = min(1, target_k / model_k). The factor is used where
        floor_w > 0 and the star's own model is FLOOR_GLOW_SIGMA bright (smoothstep
        weight, the same gates as the ring floor), smoothed in ln r (Gaussian of
        SHAPE_SMOOTH_DLNR, weighted), so it ramps to 1 with no rim. Returns
        {star: (ln r grid in arcsec, (nc, n) factor)} for the stars it changes."""
        rg, geom, nc = self.rg, self.geom, self.nc
        out = {}
        if rings is None:
            return out
        sbg = float(np.mean(self.sig_bg))
        lmid = np.log(np.maximum(rg.mid, 1e-6))
        nmin, fmin = 0, 1.0
        for i in np.nonzero(cast & self.inside)[0]:
            sr = rings.get(int(i))
            if sr is None or sr.flo is None:
                continue
            F = s_c[i] * self.Fpred[i]
            mod = np.array([F[c] * geom.A_px * psf.eval(rg.mid, c) for c in range(nc)])
            gl = np.mean(mod, axis=0) / max(sbg, 1e-30)
            wg = smoothstep((gl - SHAPE_GLOW_SIGMA[0]) / (SHAPE_GLOW_SIGMA[1] - SHAPE_GLOW_SIGMA[0])) * rg.floor_w
            wg = np.where(sr.ok, wg, 0.0)
            if not np.any(wg > 0):
                continue
            strong = np.nonzero(gl >= GUARD_END_SIGMA)[0]
            r1 = rg.mid[strong[-1]] if strong.size else rg.mid[0]
            fac = np.ones((nc, rg.n))
            changed = False
            for c in range(nc):
                mc = sr.med_c[c] if sr.med_c is not None else sr.med[c]
                sk = sr.ok & np.isfinite(mc) & (rg.mid >= r1) & (rg.mid <= 2 * r1)
                ped = max(float(np.median((mc - mod[c])[sk])), 0.0) if np.count_nonzero(sk) >= 3 else 0.0
                fl = sr.flo[c]
                ok = (wg > 0) & np.isfinite(fl) & (mod[c] > 0)
                if not ok.any():
                    continue
                ratio = np.ones(rg.n)
                ratio[ok] = np.clip((fl[ok] - ped) / mod[c][ok], 1e-3, 1.0)
                lr = np.where(ok, np.log(ratio), 0.0)
                wk = np.where(ok, wg, 0.0)
                # weighted Gaussian smoothing in ln r; rings without a floor count as 1
                d = (lmid[:, None] - lmid[None, :]) / SHAPE_SMOOTH_DLNR
                ker = np.exp(-0.5 * d * d)
                num = ker @ (wk * lr)
                den = ker @ np.maximum(wk, 1e-12)
                ls = np.where(den > 1e-9, num / den, 0.0)
                ws = np.clip((ker @ wk) / np.maximum(ker.sum(axis=1), 1e-12), 0.0, 1.0)   # smoothed weight
                f_ = np.exp(np.minimum(ls, 0.0) * ws)
                fac[c] = f_
                changed = changed or bool(np.any(f_ < 0.999))
            if changed:
                out[int(i)] = (lmid, fac)
                nmin += 1
                fmin = min(fmin, float(np.min(fac)))
        if out:
            self.R.info(f"Inner profile from the ring floor: {nmin} casters, smallest factor {fmin:.3f}")
        self.R.number("inner_shapes", {"n": nmin, "min_factor": fmin})
        return out

    def unrefined_bound(self, idx):
        """SPEC (round 17): per-channel flux factors (<= 1) for casters whose rings
        cannot check their prediction. The no-undershoot rule applied to the flux:
        10^(-0.4 UNREF_K sigma_c), sigma_c the star's honest prediction error (route B:
        its prior; XP: the field's sigma_agree with the XP bright-end error; Teff or
        no colour: sigma_agree with the Teff-route scatter), times the ratio to a second
        valid route when that is dimmer. Never dimmer than REFINE_DIM_MAX (the
        refinement's own lower bound), never above 1 (so never brighter than a refined
        star could have been)."""
        g = self.table.g[idx]
        sa = np.nan_to_num(np.asarray(self.cal.sigma_agree, float))[None, :]
        col = self.colour[idx]
        g0, s_lo, s_hi = UNREF_SIG_XP
        sxp = np.where(g < g0, s_lo, s_hi)[:, None]
        sig = np.where((col == "xp")[:, None], np.sqrt(sa ** 2 + sxp ** 2), np.sqrt(sa ** 2 + UNREF_SIG_TEFF ** 2))
        ps = self.prior_sig[idx]
        hip = (col == "hip")[:, None] & np.isfinite(ps)
        sig = np.where(hip, ps, sig)
        # offline fallback: unsaturated detections carry their measured flux
        sig = np.where(((col == "det") & (self.rsat[idx] == 0))[:, None], 0.0, sig)
        f = 10.0 ** (-0.4 * np.minimum(UNREF_K * sig, REFINE_DIM_MAX))
        alt = self.alt_ratio[idx]
        f = np.where(np.isfinite(alt), np.minimum(f, alt), f)
        return np.clip(f, 10.0 ** (-0.4 * REFINE_DIM_MAX), 1.0)

    def overlapping(self, cast, Rg):
        idx = np.nonzero(cast)[0]
        if idx.size < 2:
            return False
        xy = np.column_stack([self.xs[idx], self.ys[idx]])
        tree = cKDTree(xy)
        rmax_px = np.max(Rg[idx]) / self.geom.scale * 1.5
        for a, j in enumerate(idx):
            for b_ in tree.query_ball_point(xy[a], rmax_px):
                k = idx[b_]
                if k <= j:
                    continue
                d = self.geom.r_arcsec(self.xs[k] - self.xs[j], self.ys[k] - self.ys[j])
                if d < min(Rg[j], Rg[k]):
                    return True
        return False

    def render_and_protect(self, psf, cast, Rg, s_i):
        p, R, geom, ctx = self.p, self.R, self.geom, self.ctx
        nc, h, w = self.nc, self.h, self.w
        idx = np.nonzero(cast)[0]
        # SPEC (round 17): the model, the own-light cap, the protection zones, the
        # clamp's glow-free background and the no-dip fill all run on the central
        # fluxes (exactly as in 1.2.1); the unrefined casters' lower bound is applied
        # at the end as a pixel-wise reduction by their rendered flux difference, so
        # the subtraction can only be smaller than the central one, never larger. A
        # dimmed model fed to those stages had made them subtract more at ~1000 px
        # per channel (up to 2.4 sigma beside zeta Ori's core on Alnitak).
        s_b = s_i
        s_i = getattr(self, "s_central", s_i)
        # SPEC (round 20): each bright caster's inner profile follows its own ring floor
        shp = getattr(self, "star_shapes", None) or {}
        stars = [RenderStar(self.xs[i], self.ys[i], s_i[i] * self.Fpred[i], float(Rg[i]), taper=True,
                            shape=shp.get(int(i))) for i in idx]
        model = self.renderer.render(stars, psf.pfun(), ctx)
        self.model_final = model
        dl = [i for i in idx if np.any(s_i[i] > s_b[i])]
        delta = None
        if dl:
            delta = self.renderer.render([RenderStar(self.xs[i], self.ys[i], (s_i[i] - s_b[i]) * self.Fpred[i],
                                                     float(Rg[i]), taper=True, shape=shp.get(int(i)))
                                          for i in dl], psf.pfun(), ctx)
        bound_px = 0.0
        b = self.renderer.b
        # coarse luminance of img - bg for the cap
        Lc = None
        for c in range(nc):
            v = self.img[c] - self.bg_full(c)
            med, _ = masked_block_median(v, self.ring_valid, b)
            Lc = med / nc if Lc is None else Lc + med / nc
            del v
        cvalid = np.isfinite(masked_block_median(self.ring_valid.astype(np.float32),
                                                 self.ring_valid & ~self.core_mask, b)[0])
        sigL = float(np.sqrt(np.sum(self.sig_bg ** 2))) / nc
        f, held, sig_cap = own_light_cap(model, Lc, cvalid, sigL, R)
        # SPEC (round 11): the native-resolution clamp supersedes the coarse cap on
        # real data (0.0% held on three test images); the line is only shown
        # when the cap did something. The number is still recorded.
        if held >= 5e-4:
            R.info(f"Held to own light: {100 * held:.1f}% of the model flux")
        R.number("held_own_light", held)
        f_up = np.empty((h, w), np.float32)
        for y0 in range(0, h, 512):
            f_up[y0:y0 + 512] = upsample_coarse(f, b, (h, w), y0, min(h, y0 + 512))
        # protection
        # SPEC (round 11): every caster whose core disc (saturated disc + 2 FWHM)
        # touches the frame gets a protection zone, whether or not its centre
        # counts as "in frame": the fill-aware in_frame rule put a saturated
        # star whose centroid fell on the first empty-border row of one channel
        # outside the frame, its full model core was rendered on the valid rows
        # of the other channels, and the output went negative (bubble-rgb,
        # star at 585,4157). self.inside keeps its other roles (calibration,
        # rings, checks).
        rd_all = self.rsat[idx] + 2 * self.fwhm_px
        with np.errstate(invalid="ignore"):
            touches = (np.isfinite(self.xs[idx]) & np.isfinite(self.ys[idx])
                       & (self.xs[idx] >= -0.5 - rd_all) & (self.xs[idx] <= w - 0.5 + rd_all)
                       & (self.ys[idx] >= -0.5 - rd_all) & (self.ys[idx] <= h - 0.5 + rd_all))
        inf = [k for k in range(len(idx)) if touches[k]]
        T = p.protect
        P_i = np.array([np.mean([s_i[idx[k], c] * self.Fpred[idx[k], c] * psf.p0[c] * geom.A_px
                                 for c in range(nc)]) for k in inf])
        T_i = T * np.clip(P_i / (PROTECT_GROWTH_DIV * T), 1, PROTECT_GROWTH_MAX) ** (1 - p.brightprotect)
        rdisc = np.array([self.rsat[idx[k]] + 2 * self.fwhm_px for k in inf])
        rdisc_all = {int(idx[k]): float(rd_) for k, rd_ in zip(inf, rdisc)}
        L_all = np.zeros((h, w), np.float32)
        for c in range(nc):
            Gc = model.native(c) * f_up
            L_all += (self.img[c] - self.bg_full(c) - Gc) / nc
            del Gc
        M, zone, per_star = protection_mask(L_all, model, inf, T_i, rdisc, self.fwhm_px, ctx)
        del L_all
        self.M = M
        # SPEC (round 5): the no-dip fill may give back only the caster's own
        # subtracted model (see no_dip_correction)
        self._own_ctx = (model, f_up, {int(k_): (a0, a1, b0, b1, Ml) for (k_, a0, a1, b0, b1, Ml) in per_star},
                         1.0, {int(i_): k for k, i_ in enumerate(idx)})
        out = np.empty_like(self.img)
        glow = np.empty_like(self.img)
        GLsum = np.zeros((h, w), np.float32)
        # SPEC (round 18): from here on the channels are processed one after the
        # other; the background cache keeps only the current one
        self._bg_cache_limit = 1
        held_px = 0.0
        tot_px = 0.0
        net_px = 0
        for c in range(nc):
            ctx.check_cancel()
            Gc = model.native(c) * f_up
            GLsum += Gc / nc
            want = Gc.copy()
            for (k_, a0, a1, b0, b1, Mloc) in per_star:
                X_, Y_ = np.meshgrid(np.arange(b0, b1, dtype=np.float64), np.arange(a0, a1, dtype=np.float64))
                own_k = model.own(k_, c, X_, Y_) * f_up[a0:a1, b0:b1]
                want[a0:a1, b0:b1] -= (1.0 - Mloc) * own_k
            np.maximum(want, 0, out=want)
            # SPEC (round 21): the safety stages run on the full model; the amount is
            # applied afterwards as a plain factor (apply_amount)
            # SPEC (round 19): the lane guard on the request (see floor_guard). SPEC (round
            # 20): only in the steep zone next to the cores (CLAMP_STEEP_SIGMA[0] of the
            # star's own glow): with the inner profile from each star's ring floor
            # (inner_shapes) it finds no lanes beyond it that the output pass does not,
            # but without it the clamp left a ring of dark pixels at the protection edge
            self.floor_guard(c, None, want, idx, rdisc_all, Rg, pre=True)
            # SPEC (round 3): final no-undershoot clamp, per channel, smooth.
            # The subtraction may never take the smoothed light below the
            # glow-free local background B_c (joint-fit polynomial + the
            # large-scale residual measured away from the glow) minus a small
            # noise allowance:  G <= max(L_c - B_c, 0) + eps_c, applied with a
            # smooth minimum so that it creates no edges or blocks. Undershoot of
            # any size shows as a dark ring after a hard stretch, so the design
            # prefers under-correction (user requirement, round 3).
            cap, eps, net = self.clamp_cap(c, want)
            glow[c] = smooth_min(want, cap, 2 * eps)
            # SPEC (round 11): pixel-wise safety net. The smooth clamp estimates the
            # light from the valid neighbours and is blind on pixels that have
            # none (saturated cores): there it passed the model through and a
            # saturated star without a protection zone came out negative. No
            # pixel may now lose more than the light it holds above the local
            # background plus a noise allowance (see clamp_cap for its size).
            net_px += int(np.count_nonzero(glow[c] > net))
            np.minimum(glow[c], net, out=glow[c])
            held_px += float(np.sum(want - glow[c]))
            tot_px += float(np.sum(want))
            out[c] = self.img[c] - glow[c]
            del Gc, want, cap, net
            self.no_dip_correction(c, out, glow, idx, rdisc_all, Rg)
            self.floor_guard(c, out, glow, idx, rdisc_all, Rg)
            if delta is not None:
                # SPEC (round 17): lower bound of the unrefined casters
                red = np.minimum(delta.native(c) * f_up, glow[c])
                np.maximum(red, 0, out=red)
                glow[c] -= red
                out[c] += red
                bound_px += float(np.sum(red))
                del red
            if getattr(self, "fill", None) is not None:
                glow[c][self.fill] = 0.0
                out[c][self.fill] = self.img[c][self.fill]
        clamp_frac = held_px / tot_px if tot_px > 0 else 0.0
        if delta is not None:
            R.info(f"Lower bound of {len(dl)} unrefined casters: {bound_px:.4g} (image units x px) less "
                   "subtracted")
            R.number("bound_reduction", bound_px)
        R.info(f"No-undershoot clamp: {100 * clamp_frac:.1f}% of the requested glow held back "
               "(model above the light present)")
        R.number("clamp_held", clamp_frac)
        R.info(f"Pixel safety net (glow <= light + {CLAMP_NET_K:.0f} sigma): acted on {net_px} pixels")
        R.number("net_pixels", net_px)
        # SPEC: P2 is evaluated on the glow regime (pixels where the model is
        # between 0.5 sigma_bg and T): the cores carry most of the model flux and
        # are protected by design, so a flux fraction would always exceed 90%.
        sigL0 = float(np.sqrt(np.sum(self.sig_bg ** 2))) / nc
        gz = (GLsum > 0.5 * sigL0) & (GLsum < T)
        frac_prot = float(np.sum(GLsum[gz] * (1 - M[gz])) / max(1e-30, float(np.sum(GLsum[gz]))))
        del GLsum
        R.number("protected_fraction", frac_prot)
        # SPEC (round 11): the warning is not shown for now. With automatic
        # selection the statistic is dominated by the feathered discs of
        # thousands of faint casters and fired on default parameters (94% on
        # M31); the number is kept for a later redefinition.
        if frac_prot > P2_PROTECTED:
            R.info(f"{100 * frac_prot:.0f}% of the model flux in the glow regime lies in protected zones")
        GL = np.mean(glow, axis=0)
        bgL = np.mean([np.median(self.bg_rows(c, h // 2, h // 2 + 1)) for c in range(nc)])
        pk = float(np.max(GL))
        R.info(f"Glow removed: total {float(np.sum(glow)):.4g} (image units x px), peak "
               f"{pk:.3g} = {pk / max(sigL, 1e-12):.1f} sigma_bg"
               + (f" = {100 * pk / bgL:.1f}% of the background" if bgL > 0 else ""))
        R.number("glow_removed", {"total": float(np.sum(glow)), "peak": pk,
                                  "peak_sigma": pk / max(sigL, 1e-12)})
        return out, glow

    def no_dip_correction(self, c, out, glow, idx, rdisc_all, Rg):
        """SPEC (round 3): no dark ring. Around each of the brightest in-frame
        casters, the azimuthally robust residual profile (median of 8 sector
        medians per ring, so spikes and rays are ignored) of out - B_c must not
        increase outwards: a dip below the level further out is a dark ring
        after a stretch, even when it lies above the background. Each dip is
        removed by adding back the missing amount (never more than was
        subtracted there), interpolated smoothly in r. The symmetric model
        stays; only its over-subtraction near the core is reduced.
        SPEC (round 13): the profile is taken over all valid pixels (the
        pixels with glow > 0 alone are, where the clamp acts sparsely, the
        bright subset and read high), the level of the untouched rings beyond
        the modelled ones is removed first (it is background-model error, not
        glow, and B_c was 0.3-0.4 sigma below the local sky under the bright
        stars of a nebula field), and the dip test runs only on the rings
        where the model was subtracted. Without this the outer level set by
        the unmodelled far wing was a floor every inner ring was lifted to,
        and the far glow (60-200 px) of the bright stars was given back
        entirely on bubble-rgb (118 units against 1.5 on M31)."""
        h, w = self.h, self.w
        order = sorted([int(i) for i in idx if self.inside[i]], key=lambda i: -float(np.sum(self.Fpred[i])))
        order = order[:NODIP_MAX_STARS]
        B = self.local_background(c)
        sig = float(self.sig_bg[c])
        added = 0.0
        for i in order:
            cx, cy = float(self.xs[i]), float(self.ys[i])
            r0 = max(rdisc_all.get(i, self.rsat[i] + 2 * self.fwhm_px), 2.0)
            r1 = min(float(Rg[i]) / self.geom.scale, 1.5 * max(h, w))
            if r1 <= 1.5 * r0:
                continue
            x0, x1 = max(0, int(cx - r1)), min(w, int(cx + r1) + 1)
            y0, y1 = max(0, int(cy - r1)), min(h, int(cy + r1) + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            step = max(1, int(r1 // 600))
            yy, xx = np.mgrid[y0:y1:step, x0:x1:step]
            rr = np.hypot(xx - cx, yy - cy)
            edges = np.geomspace(r0, r1, NODIP_RINGS + 1)
            lab = np.searchsorted(edges, rr) - 1
            sec = np.clip(((np.arctan2(yy - cy, xx - cx) + np.pi) / (2 * np.pi) * N_SECTORS).astype(int),
                          0, N_SECTORS - 1)
            # SPEC (round 18): strided slices instead of fancy indexing (same pixels)
            win = (slice(y0, y1, step), slice(x0, x1, step))
            okp = (lab >= 0) & (lab < NODIP_RINGS) & self.ring_valid[win]
            res = (out[c][win] - B[win])[okp]
            gv = glow[c][win][okp]
            labv, secv = lab[okp], sec[okp]
            prof = np.full(NODIP_RINGS, np.nan)
            gprof = np.full(NODIP_RINGS, np.nan)
            # SPEC (round 18): grouped medians (one sort per array) instead of
            # one np.median per ring and sector; same values
            nring = np.bincount(labv, minlength=NODIP_RINGS)
            smed, scnt = grouped_median_of(res, labv * N_SECTORS + secv, NODIP_RINGS * N_SECTORS)
            smed, scnt = smed.reshape(NODIP_RINGS, N_SECTORS), scnt.reshape(NODIP_RINGS, N_SECTORS)
            rk = np.nonzero(nring >= 16)[0]
            gmed = None
            for rows, A in rowwise_stats(smed[rk], scnt[rk] >= 2, 3):
                if gmed is None:
                    gmed = grouped_median_of(gv, labv, NODIP_RINGS)[0]
                k = rk[rows]
                prof[k] = np.median(A, axis=1)
                gprof[k] = gmed[k]
            good = np.isfinite(prof)
            mid = np.sqrt(edges[:-1] * edges[1:])
            # SPEC (round 13): modelled rings (the model was subtracted there)
            # are tested; the untouched rings beyond them give the level that
            # is removed first
            modelled = good & (gprof >= NODIP_MIN_SIGMA * sig)
            if modelled.sum() < 3:
                continue
            outer = good & ~modelled & (mid > mid[modelled].max())
            if outer.sum() >= 2:
                prof = prof - float(np.median(prof[outer]))
            good = modelled
            p_ = np.interp(np.log(mid), np.log(mid[good]), prof[good])
            sm = p_.copy()
            sm[1:-1] = np.median(np.vstack([p_[:-2], p_[1:-1], p_[2:]]), axis=0)
            env = np.maximum.accumulate(sm[::-1])[::-1]       # outside-in running maximum
            dip = np.maximum(env - sm, 0.0)
            dip[dip < NODIP_MIN_SIGMA * sig] = 0.0
            if not np.any(dip > 0):
                continue
            # smooth radial add-back on the full-resolution cutout
            # SPEC (round 5): give back at most this caster's own subtracted
            # model. Limited only by the total model, the fill around a faint
            # star inside a bright star's halo removed the bright star's glow
            # too: hard-edged zero discs in the model, unsubtracted (+2 sigma)
            # discs in the output.
            own_ctx = getattr(self, "_own_ctx", None)
            if own_ctx is not None:
                model_, f_up_, masks_, amount_, kmap_ = own_ctx
                k_ = kmap_.get(int(i))
                if k_ is None:
                    continue
                Ml_ = masks_.get(k_)
            # SPEC (round 18): evaluated in bands of NODIP_ROWS rows on broadcast
            # coordinates (the same operations per pixel) instead of on full-cutout
            # float64 grids: for zeta Ori on Alnitak the cutout is the whole frame
            # and its temporaries set the run's memory peak (+1.8 GB)
            add = np.empty((y1 - y0, x1 - x0), np.float32)
            xr = np.arange(x0, x1, dtype=np.float64)[None, :]
            lmid = np.log(mid)
            for ya in range(y0, y1, NODIP_ROWS):
                yb = min(y1, ya + NODIP_ROWS)
                yr = np.arange(ya, yb, dtype=np.float64)[:, None]
                rf = np.hypot(xr - cx, yr - cy)
                a_ = np.interp(np.log(np.maximum(rf, mid[0])), lmid, dip,
                               left=dip[0], right=0.0).astype(np.float32)
                a_[rf > r1] = 0
                del rf
                if own_ctx is not None:
                    own = model_.own(k_, c, xr, yr) * f_up_[ya:yb, x0:x1] * np.float32(amount_)
                    if Ml_ is not None:
                        a0, a1, b0, b1, Ml = Ml_
                        ya0, ya1, xb0, xb1 = max(a0, ya), min(a1, yb), max(b0, x0), min(b1, x1)
                        if ya0 < ya1 and xb0 < xb1:
                            own[ya0 - ya:ya1 - ya, xb0 - x0:xb1 - x0] *= Ml[ya0 - a0:ya1 - a0, xb0 - b0:xb1 - b0]
                    a_ = np.minimum(a_, own.astype(np.float32))
                    del own
                add[ya - y0:yb - y0] = np.minimum(a_, glow[c][ya:yb, x0:x1])
            out[c][y0:y1, x0:x1] += add
            glow[c][y0:y1, x0:x1] -= add
            added += float(np.sum(add))
        if added > 0:
            self.R.info(f"No-dark-ring correction, channel {c}: {added:.4g} (image units x px) of "
                        "subtraction given back near cores")
        del B

    def floor_guard(self, c, out, glow, idx, rdisc_all, Rg, pre=False):
        """SPEC (round 19): no dark lanes, whatever the fit did. The no-dip test and
        the undershoot check work on 45-degree sector medians and the clamp on a
        smoothed light map: none of them sees a lane a few degrees wide, and the
        lanes next to the cores (8-40 px on M31, glow 20-200 sigma, where a 1-2 %
        model excess is 1-2 sigma) survived the ring floor of the fit. For each
        caster (see the GUARD_* constants), brightest first: the floor F_out of
        out - B_c per radial band (noise-corrected minimum of fine azimuth bins,
        RingMeasurer._ring_floor) and the same floor F_in of the input. The
        reference is min(0, F_in) (plus GUARD_MARGIN pixel sigma, at most F_in):
        never below the background, unless the input itself lay lower there.
        SPEC (round 20): both are taken relative to the local sky, B_c raised to a
        plane fitted to the residual in [r1, 2 r1] (see below), and no deficit is
        tolerated (GUARD_Z = 0). (The
        level just beyond the guarded radius as a local-sky reference, as in
        no_dip_correction, gave back 0.17 of the crop's 6.9 units of glow in the
        faint outskirts of the casters for no visible change near the cores.)
        The deficit beyond GUARD_Z times the floor's noise is
        dilated by one band, interpolated in r, and given back on all azimuths,
        at most this star's own subtracted model there (as in no_dip_correction),
        so the model stays symmetric and only under-corrects.
        pre=True runs the same test on the requested subtraction before the clamp
        (out is None, glow is the request want of channel c, 2-D): the residual
        img - B_c - want is flat where the model is right, so a model above the
        floor is seen as such, and cut, before the clamp holds it on a smoothed
        light map (which left rings of dark pixels where the model exceeded the
        light by tens of sigma, M31 at 12-13 px)."""
        own_ctx = getattr(self, "_own_ctx", None)
        if own_ctx is None:
            return
        model_, f_up_, masks_, amount_, kmap_ = own_ctx
        h, w = self.h, self.w
        sig = float(self.sig_bg[c])
        B = self.local_background(c)
        vfn = self.valid_native_fn()
        order = sorted([int(i) for i in idx if self.inside[i]], key=lambda i: -float(np.sum(self.Fpred[i])))
        order = order[:GUARD_MAX_STARS]
        rl = np.geomspace(1.0, GUARD_MAX_PX, 240)
        added, nfix = 0.0, 0
        for i in order:
            k_ = kmap_.get(int(i))
            if k_ is None:
                continue
            cx, cy = float(self.xs[i]), float(self.ys[i])
            r0 = max(rdisc_all.get(i, self.rsat[i] + 2 * self.fwhm_px), 2.0)
            prof = model_.own(k_, c, cx + rl, np.full_like(rl, cy)) * float(amount_)
            if float(np.interp(r0, rl, prof)) < GUARD_MIN_SIGMA * sig:
                continue
            strong = prof >= (CLAMP_STEEP_SIGMA[0] if pre else GUARD_END_SIGMA) * sig
            if not strong.any():
                continue
            r1 = min(float(rl[strong].max()), float(Rg[i]) / self.geom.scale, GUARD_MAX_PX)
            if r1 <= 1.2 * r0:
                continue
            e = [r0]
            while e[-1] < r1:
                e.append(e[-1] + max(GUARD_DR_PX, GUARD_DLNR * e[-1]))
            e = np.array(e)
            nr = e.size - 1
            ro = 2.0 * e[-1]     # SPEC (round 20): room for the local-sky annulus [r1, 2 r1]
            x0, x1 = max(0, int(cx - ro)), min(w, int(cx + ro) + 2)
            y0, y1 = max(0, int(cy - ro)), min(h, int(cy + ro) + 2)
            if x0 >= x1 or y0 >= y1:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float64), np.arange(y0, y1, dtype=np.float64))
            rr = np.hypot(X - cx, Y - cy)
            v_ok, _ = vfn(y0, y1, x0, x1, cx, cy)
            if pre:
                res = self.img[c][y0:y1, x0:x1] - B[y0:y1, x0:x1] - glow[y0:y1, x0:x1]
            else:
                res = out[c][y0:y1, x0:x1] - B[y0:y1, x0:x1]
            lab = np.searchsorted(e, rr, side="right") - 1
            use = v_ok & (lab >= 0) & (lab < nr)
            # SPEC (round 20): the local sky. B_c can lie well below the sky under a
            # bright star (1e-5, 3 sigma, on the user's 2414 x 1687 crop next to the
            # galaxy: B_c 0.000533 against a sky of 0.000540-0.000543), and the clamp
            # lets the output down to B_c: the lanes sat there. A plane fitted
            # (3-sigma clipped) to the residual in the annulus [r1, 2 r1] just beyond
            # the guarded radius gives the sky across the star; it raises the
            # reference where it lies above B_c, never lowers it.
            sky = v_ok & (rr >= e[-1]) & (rr < ro)
            skyp = np.zeros(res.shape)
            if np.count_nonzero(sky) >= 50:
                A_ = np.column_stack([np.ones(int(np.count_nonzero(sky))), X[sky] - cx, Y[sky] - cy])
                v_ = res[sky].astype(np.float64)
                kp = np.ones(v_.size, bool)
                cf = np.zeros(3)
                for _ in range(4):
                    cf = np.linalg.lstsq(A_[kp], v_[kp], rcond=None)[0]
                    r_ = v_ - A_ @ cf
                    s_ = 1.4826 * float(np.median(np.abs(r_[kp] - np.median(r_[kp]))))
                    kp = np.abs(r_) <= 3 * max(s_, 1e-30)
                skyp = np.maximum(cf[0] + cf[1] * (X - cx) + cf[2] * (Y - cy), 0.0)
            res = res - skyp
            if not use.any():
                continue
            lv = lab[use]
            fb = RingMeasurer._sectors(X[use], Y[use], cx, cy)
            cnt = np.bincount(lv, minlength=nr)
            fl = []
            for vals in (res[use], self.img[c][y0:y1, x0:x1][use] - B[y0:y1, x0:x1][use] - skyp[use]):
                vals = vals.astype(np.float64)
                o = group_order(vals, lv, nr)
                flo, fnb, fsb = np.full(nr, np.nan), np.zeros(nr), np.full(nr, np.nan)
                RingMeasurer._ring_floor(vals[o], lv[o], fb[o] % FLOOR_BINS, fb[o] // FLOOR_BINS, cnt,
                                         np.ones(nr, bool), flo, fnb, fsb)
                fe, fsd = RingMeasurer.floor_noise(np.maximum(fnb, 2))
                fl.append((flo - fe * np.nan_to_num(fsb), fsd * np.nan_to_num(fsb),
                           MEDIAN_EFF_INV * np.nan_to_num(fsb) * np.sqrt(cnt / np.maximum(fnb, 1))))
            (f_out, sd_out, spix), (f_in, _, _) = fl
            ref = np.where(np.isfinite(f_in), np.minimum(0.0, f_in), 0.0)
            # where the star's own subtraction is steep (CLAMP_STEEP_SIGMA, the
            # regime in which a percent of model error exceeds the noise), the floor
            # is kept GUARD_MARGIN pixel sigma (measured, shot noise included) above
            # the reference, never above the input's floor: a floor exactly at the
            # background next to a bright core reads as a dark rim
            mid0 = 0.5 * (e[:-1] + e[1:])
            stp = self._clamp_steep_weight(np.interp(mid0, rl, prof).astype(np.float32), sig).astype(np.float64)
            ref = np.where(np.isfinite(f_in), np.minimum(ref + GUARD_MARGIN * stp * spix, f_in), ref)
            # SPEC (round 20): no allowance (GUARD_Z = 0): any coherent dip shows after a
            # strong stretch; the noise-bias correction of the minimum stays
            dfc = np.nan_to_num(ref - f_out - GUARD_Z * sd_out, nan=0.0)
            dfc = np.maximum(dfc, 0.0)
            if not np.any(dfc > 0):
                continue
            d2 = dfc.copy()
            d2[1:] = np.maximum(d2[1:], dfc[:-1])
            d2[:-1] = np.maximum(d2[:-1], dfc[1:])
            mid = 0.5 * (e[:-1] + e[1:])
            Ml_ = masks_.get(k_)
            ya, yb = max(0, int(cy - e[-1]) - 1), min(h, int(cy + e[-1]) + 2)
            xa, xb = max(0, int(cx - e[-1]) - 1), min(w, int(cx + e[-1]) + 2)
            xr = np.arange(xa, xb, dtype=np.float64)[None, :]
            yr = np.arange(ya, yb, dtype=np.float64)[:, None]
            rf = np.hypot(xr - cx, yr - cy)
            a_ = np.interp(rf, mid, d2, left=d2[0], right=0.0).astype(np.float32)
            a_[rf > e[-1]] = 0
            # SPEC (round 20): tapered to 0 over the outer GUARD_TAPER of the guarded
            # radius: a give-back that ended at r1 at full height (a sky offset is the
            # same at all radii) was drawn as a disc around the star
            a_ *= smoothstep((e[-1] - rf) / (GUARD_TAPER * e[-1])).astype(np.float32)
            own = model_.own(k_, c, xr, yr) * f_up_[ya:yb, xa:xb] * np.float32(amount_)
            if Ml_ is not None:
                a0, a1, b0, b1, Ml = Ml_
                ya0, ya1, xb0, xb1 = max(a0, ya), min(a1, yb), max(b0, xa), min(b1, xb)
                if ya0 < ya1 and xb0 < xb1:
                    own[ya0 - ya:ya1 - ya, xb0 - xa:xb1 - xa] *= Ml[ya0 - a0:ya1 - a0, xb0 - b0:xb1 - b0]
            gw = glow[ya:yb, xa:xb] if pre else glow[c][ya:yb, xa:xb]
            add = np.minimum(np.minimum(a_, own.astype(np.float32)), gw)
            np.maximum(add, 0, out=add)
            gw -= add
            if not pre:
                out[c][ya:yb, xa:xb] += add
            added += float(np.sum(add))
            nfix += 1
        tag = "before the clamp" if pre else "after the clamp"
        if added > 0:
            self.R.info(f"Lane guard ({tag}), channel {c}: {nfix} casters, {added:.4g} (image units x px) "
                        "of subtraction given back where the azimuthal floor fell below the background")
        self.R.number(f"lane_guard_{'pre' if pre else 'post'}_{c}", {"stars": nfix, "given_back": added})
        del B

    def glow_free_residual(self):
        """Large-scale residual of the joint fit measured where the final model
        is negligible (< 0.05 sigma), filled by normalised convolution: the sky
        structure the polynomial misses, without the glow."""
        if getattr(self, "_res_far", None) is not None:
            return self._res_far
        jb = self.jb
        out = []
        cm = self.model_final.coarse
        for c in range(self.nc):
            g_ = self.wf[c].residual.reshape(jb.nby, jb.nbx).astype(np.float32)
            # model at block centres (coarse grid -> block grid by nearest cell)
            yc = np.clip(((np.arange(jb.nby) + 0.5) * jb.b / self.renderer.b).astype(int), 0, cm.shape[1] - 1)
            xc = np.clip(((np.arange(jb.nbx) + 0.5) * jb.b / self.renderer.b).astype(int), 0, cm.shape[2] - 1)
            mod = cm[c][np.ix_(yc, xc)]
            g_ = np.where(mod < 0.05 * self.sig_bg[c], g_, np.nan)
            if np.isfinite(g_).sum() < 10:
                out.append(np.zeros_like(g_))
                continue
            out.append(normalised_convolution_fill(g_, CLAMP_BG_SIGMA_BLOCKS))
        self._res_far = out
        return out

    def local_background(self, c):
        """Glow-free local background B_c at native resolution.
        SPEC (round 3): the higher of the bases-fit background and the current
        (template-refitted) one. A refit that claims too much light for the
        wing lowers the polynomial below the true sky, and a clamp at that
        level would allow undershoot; the bases fit absorbs wing light and
        errs high, i.e. towards under-correction."""
        rf = self.glow_free_residual()[c]
        jb = self.jb
        up = np.empty((self.h, self.w), np.float32)
        for y0 in range(0, self.h, 512):
            up[y0:y0 + 512] = upsample_coarse(rf, jb.b, (self.h, self.w), y0, min(self.h, y0 + 512))
        bg = self.bg_full(c)
        wb = getattr(self, "wf_bases", None)
        if wb is not None and wb[c] is not self.wf[c]:
            bg = np.maximum(bg, eval_poly_image(wb[c].poly, self.p.bgorder, self.h, self.w))
        return bg + up

    def clamp_cap(self, c, want):
        """Upper limit of the subtraction for channel c:
            cap = max(want + S[img - B_c - want], 0) + eps_c
        where S is a masked (normalised) Gaussian smoothing over non-core
        pixels. Smoothing the nearly flat residual instead of the light itself
        avoids the curvature bias of smoothing a steep profile (a few per cent
        of a glow that is hundreds of sigma near a bright star). The output then
        satisfies out - B_c >= (residual - S[residual]) - eps_c: pixel noise
        only, never a smooth dark ring.
        SPEC (round 11): also returns the pixel-wise safety net
            net = max(img - B_c, 0) + CLAMP_NET_K sigma_bg sqrt(1 + max(img - B_c, 0) / sky)
        applied after the smooth minimum. It bounds the subtraction on every
        pixel, including the saturated ones the smooth estimate cannot see.
        k = 5 keeps it clear of the noise: the clamp leaves out - B_c at
        (pixel noise - eps), and a net at k sigma truncates that noise below
        -k sigma; with the sky-limited shot-noise scaling (exact for a plain
        stack, a lower bound for HDR composites) the truncated fraction stays
        below ~1% where the light is a few times the sky, while a saturated
        core (light ~ 1, sky ~ 0.005) is still bounded at light + ~0.01."""
        light = self.img[c] - self.local_background(c)
        # only saturated / invalid pixels are excluded: the core masks used for
        # the rings would leave the ring just outside a protection zone without
        # a clamp (star light is a positive outlier the percentile branch skips)
        valid = self.ring_valid
        sg = float(self.sig_bg[c])
        eps = CLAMP_K * self.sig_bg[c] * math.sqrt(self.eta) / (2 * math.sqrt(math.pi) * CLAMP_SMOOTH_PX)
        # SPEC (round 18): the filters run on bands of CLAMP_BAND rows, each with
        # CLAMP_HALO rows of margin, instead of on the full frame: the eight
        # filter temporaries shrink from full frames to bands. Every filter
        # output depends only on the input within its radius (24 px for the
        # whole chain), and the frame edges keep their "nearest" extension, so
        # the cap is unchanged. Bands without requested glow are skipped: there
        # want = 0, and the smooth minimum gives 0 for any finite cap >= 0, so
        # the cap is left at eps. (Restricting the filters to the glow footprint
        # does not pay: thousands of casters put glow into 99% of 256 px tiles
        # on all three test images.)
        h, w = want.shape
        T, H = CLAMP_BAND, CLAMP_HALO
        bands = [(y0, min(h, y0 + T)) for y0 in range(0, h, T) if np.any(want[y0:min(h, y0 + T)] != 0)]
        steep = any(np.any(self._clamp_steep_weight(want[y0:y1], sg) > 0) for (y0, y1) in bands)
        S = np.full((h, w), np.float32(eps), np.float32)
        for (y0, y1) in bands:
            Y0, Y1 = max(0, y0 - H), min(h, y1 + H)
            St = self._clamp_smooth(light[Y0:Y1], want[Y0:Y1], valid[Y0:Y1], c, sg, steep)[y0 - Y0:y1 - Y0]
            St += want[y0:y1]
            np.maximum(St, 0, out=St)
            St += np.float32(eps)
            S[y0:y1] = St
        # the safety net (see the docstring); sky from the background at mid-frame
        np.maximum(light, 0, out=light)
        sky = max(float(np.median(self.bg_rows(c, self.h // 2, self.h // 2 + 1))), float(sg))
        # SPEC (round 18): evaluated in place (same operations, fewer temporaries)
        net = light / np.float32(sky)
        net += 1.0
        np.sqrt(net, out=net)
        net *= np.float32(CLAMP_NET_K * sg)
        net += light
        del light
        return S, eps, net.astype(np.float32, copy=False)

    @staticmethod
    def _clamp_steep_weight(want, sg):
        return smoothstep((want / max(sg, 1e-30) - CLAMP_STEEP_SIGMA[0]) /
                          (CLAMP_STEEP_SIGMA[1] - CLAMP_STEEP_SIGMA[0])).astype(np.float32)

    def _clamp_smooth(self, light, want, valid, c, sg, steep):
        """S[img - B_c - want] of clamp_cap on one window (see there)."""
        resid = light - want
        wv = ndimage.gaussian_filter(valid.astype(np.float32), CLAMP_SMOOTH_PX, mode="nearest")
        sv = ndimage.gaussian_filter(np.where(valid, resid, 0).astype(np.float32), CLAMP_SMOOTH_PX,
                                     mode="nearest")
        with np.errstate(all="ignore"):
            S = np.where(wv > 0.2, sv / wv, 0.0).astype(np.float32)
        # robust branch: a sliding 5x5 median follows the dark gaps between
        # spikes instead of averaging them with the bright spikes; a Gaussian on
        # top removes its texture; the smaller of the two estimates is used.
        # a 25th-percentile filter follows the gaps between fine spokes (a few
        # px apart) better than a median; its noise bias (-0.67 sigma for white
        # noise) is removed with a slightly smaller value (correlated stack
        # noise makes the true bias smaller), erring towards under-correction.
        rm = ndimage.percentile_filter(np.where(valid, resid, np.nan_to_num(S)).astype(np.float32),
                                       CLAMP_PERCENTILE, size=CLAMP_MEDIAN_PX, mode="nearest")
        rm += np.float32(CLAMP_PCT_BIAS * self.sig_bg[c])
        Sm = ndimage.gaussian_filter(rm, CLAMP_SMOOTH_PX / 2.0, mode="nearest")
        np.minimum(S, Sm, out=S)
        # steep branch: where the requested glow is large (tens of sigma, next to
        # bright cores) a 1-2 % model mismatch is several sigma and the gaps
        # between spikes are 1-2 px wide; a 3x3 minimum filter (noise bias of
        # the minimum of 9 samples, -1.485 sigma, removed) follows them. It is
        # blended in smoothly from 10 to 30 sigma of requested glow.
        wst = self._clamp_steep_weight(want, sg)
        if steep:
            mn = ndimage.minimum_filter(np.where(valid, resid, Sm).astype(np.float32), size=3, mode="nearest")
            mn += np.float32(1.485 * sg)
            mn = ndimage.gaussian_filter(mn, 0.75, mode="nearest")
            S -= wst * np.maximum(S - mn, 0)
            del mn
        return S

    def undershoot_check(self, out, cast, Rg):
        """SPEC (round 3): replaces the spec's over-subtraction fraction test
        (15.4). Around every in-frame caster, in log-spaced annuli x 8 sectors
        and per channel, the median of (out - B_c) over unprotected, non-core
        pixels must not fall below -UNDERSHOOT_Z sigma of that median."""
        nc, h, w = self.nc, self.h, self.w
        idx = np.nonzero(cast & self.inside)[0]
        if idx.size == 0:
            return
        idx = idx[np.argsort(-np.sum(self.Fpred[idx], axis=1))][:25]
        worst = (np.inf, None)
        nviol = 0
        ncells = 0
        for c in range(nc):
            Bc = self.local_background(c)
            diff = out[c] - Bc
            before = self.img[c] - Bc
            del Bc
            sc = self.sig_bg[c] * math.sqrt(self.eta)
            eps_c = CLAMP_K * sc / (2 * math.sqrt(math.pi) * CLAMP_SMOOTH_PX)
            for i in idx:
                cx, cy = self.xs[i], self.ys[i]
                r0 = self.rsat[i] + 3 * self.fwhm_px
                r1 = min(Rg[i] / self.geom.scale, 1.5 * max(h, w))
                if r1 <= r0 * 1.2:
                    continue
                edges = np.geomspace(max(r0, 3.0), r1, 9)
                step = max(1, int(r1 // 400))
                x0, x1 = max(0, int(cx - r1)), min(w, int(cx + r1) + 1)
                y0, y1 = max(0, int(cy - r1)), min(h, int(cy + r1) + 1)
                if x0 >= x1 or y0 >= y1:
                    continue
                yy, xx = np.mgrid[y0:y1:step, x0:x1:step]
                rr = np.hypot(xx - cx, yy - cy)
                sec = np.clip(((np.arctan2(yy - cy, xx - cx) + np.pi) / (2 * np.pi) * N_SECTORS).astype(int),
                              0, N_SECTORS - 1)
                # SPEC (round 18): strided slices instead of fancy indexing (same pixels)
                win = (slice(y0, y1, step), slice(x0, x1, step))
                ok = (self.M[win] >= 0.999) & ~self.core_mask[win] & self.ring_valid[win]
                dv = diff[win]
                bv = before[win]
                lab = np.searchsorted(edges, rr) - 1
                good = ok & (lab >= 0) & (lab < edges.size - 1)
                key = lab[good] * N_SECTORS + sec[good]
                vals = dv[good]
                bvals = bv[good]
                # SPEC (round 18): grouped medians of all cells at once (same values)
                ncell = (edges.size - 1) * N_SECTORS
                mv, cntv = grouped_median_of(vals, key, ncell)
                mb = grouped_median_of(bvals, key, ncell)[0]
                for kk in range(ncell):
                    nk = int(cntv[kk])
                    if nk < 30:
                        continue
                    # only undershoot caused by the subtraction counts: where the
                    # input already lies below B (B too high, dark structure),
                    # the reference is the input itself
                    med = float(mv[kk]) - min(0.0, float(mb[kk]))
                    # the clamp's own noise allowance is not counted as undershoot
                    z = (med + eps_c) / (MEDIAN_EFF * sc / math.sqrt(nk))
                    ncells += 1
                    if z < -UNDERSHOOT_Z:
                        nviol += 1
                    if z < worst[0]:
                        worst = (z, (c, int(i), float(edges[kk // N_SECTORS]), med / self.sig_bg[c]))
            del diff, before
        self.R.number("undershoot", {"min_z": worst[0], "cells": ncells, "violations": nviol})
        if worst[1] is None:
            return
        c, i, r_, ms = worst[1]
        self.R.info(f"No-undershoot check: {ncells} annulus x sector x channel cells around "
                    f"{idx.size} casters; worst median {ms:+.2f} sigma (z {worst[0]:+.1f}) at "
                    f"r = {r_ * self.geom.scale / 60:.1f}' in channel {c}")
        if nviol:
            self.R.warn(f"Undershoot detected in {nviol} of {ncells} cells (worst {ms:+.2f} sigma at "
                        f"{r_ * self.geom.scale / 60:.1f}'): the output falls below the local "
                        "background. Lower -amount or raise -protect.")

    def post_checks(self, out, glow, cast, Rg, psf):
        """No-undershoot check and residual profiles (spec 15.4, round 3)."""
        nc, h, w = self.nc, self.h, self.w
        self.undershoot_check(out, cast, Rg)
        # residual profile of the 3 brightest in-frame casters
        idx = np.nonzero(cast & self.inside)[0]
        if idx.size == 0:
            return
        idx = idx[np.argsort(-np.sum(self.Fpred[idx], axis=1))][:3]
        b = self.renderer.b
        work = [out[c] - self.bg_full(c) for c in range(nc)]
        valid_c = self.ring_valid & ~self.core_mask
        workc = [masked_block_median(work[c], valid_c, b)[0] for c in range(nc)]
        cvalid = np.isfinite(workc[0])
        satc = np.nan_to_num(np.nanmean(block_view((self.sat_native & ~self.core_mask).astype(np.float32), b),
                                        axis=2)[:cvalid.shape[0], :cvalid.shape[1]])
        zero = lambda X, Y: np.zeros((nc,) + np.shape(X), np.float32)
        rm = RingMeasurer((h, w), self.geom, self.rg, nc, b, self.eta, self.R)
        vfn = self.valid_native_fn()
        self.residual_profiles = {}
        # SPEC (round 19): the residual rings are valued like the rings that sized the
        # model, with the azimuthal floor where the star's own model is bright
        # (gate): the lanes the model leaves by design do not read as under-subtraction
        rm.sig_bg = np.asarray(self.sig_bg, float)
        mf = getattr(self, "model_final", None)
        kmap = (getattr(self, "_own_ctx", None) or (None,) * 5)[4] or {}
        for i in idx:
            k = kmap.get(int(i))
            gate = (lambda X, Y, k=k: mf.own_all(k, X, Y)) if (mf is not None and k is not None) else None
            sr = rm.measure(("post", int(i)), self.xs[i], self.ys[i], float(Rg[i]), work, workc, zero, zero,
                            None, None, vfn, self.sat_native, cvalid, satc, gate=gate)
            sel = sr.ok & (self.rg.mid >= 4 * self.fwhm) & (self.rg.mid <= Rg[i])
            if sel.sum() < 3:
                continue
            m = np.sum(sr.med[:, sel], axis=0) / nc
            sg = np.sqrt(np.sum(sr.sig[:, sel] ** 2, axis=0) + np.sum(self.sig_sys ** 2)) / nc
            z = float(np.median(m / sg))
            self.residual_profiles[int(i)] = (self.rg.mid[sel], m, sg)
            name = self.table.name[i] or f"G={self.table.g[i]:.2f}"
            self.R.info(f"Residual profile {name}: median {z:+.2f} sigma over [4 FWHM, R_glow]")
            if z < -2:
                self.R.warn(f"Residual rings around {name} are systematically negative "
                            f"({z:+.1f} sigma): over-subtraction.")
            elif z > 2:
                self.R.warn(f"Residual rings around {name} are strongly positive ({z:+.1f} sigma): "
                            "under-subtraction (check -protect or -tolerance).")
        del work, workc

    def summary_lines(self):
        n = self.R.numbers
        L = []
        sa = n.get("sigma_agree")
        if sa is not None:
            L.append("Catalogue agreement: " + ", ".join(f"{v:.3f}" for v in sa) + " mag")
        b = n.get("beta")
        L.append(f"Linearity slope: {b:.3f}" if isinstance(b, float) else "Linearity slope: not measurable")
        st = n.get("stars")
        if st:
            L.append(f"Stars subtracted: {st['in_frame']} in frame, {st['off_frame']} off frame, "
                     f"{st['D']} from the bright-star table")
        rc = n.get("reach")
        if rc:
            L.append(f"PSF reach: measured {rc['measured']:.1f}', joint {rc['joint']:.1f}', "
                     f"alpha {rc['alpha']:.2f}")
        # SPEC (round 11): "Held to own light" is only listed when the cap acted
        if n.get("held_own_light", 0) >= 5e-4:
            L.append(f"Held to own light: {100 * n['held_own_light']:.1f}% of model flux")
        g = n.get("glow_removed")
        if g:
            L.append(f"Glow removed: peak {g['peak_sigma']:.1f} sigma_bg")
        if getattr(self, "offline", False):
            L.insert(0, "IN-FRAME STARS ONLY, NO CATALOGUE: off-frame glow is not modelled; "
                        "photometric checks not measurable")
        return L

    # -- in-frame-only fallback (spec 4.4 step 5, decided Q8) ---------------
    def compute_offline(self, info):
        p, R, ctx, geom = self.p, self.R, self.ctx, self.geom
        nc, h, w = self.nc, self.h, self.w
        msg = ("No Gaia catalogue is available (no local catalogue and the remote catalogue is "
               "unreachable). Glow from stars outside the frame cannot be modelled.")
        if ctx.ui is not None:
            if not ctx.ui.ask("offline", msg):
                raise Cancelled("aborted: no catalogue")
        elif not p.offline_ok:
            raise HardRefusal(msg + " Use -offline-ok to continue with in-frame stars only.")
        R.warn("IN-FRAME STARS ONLY, NO CATALOGUE: " + msg)
        # Stars: detections of the reference channel, fluxes measured in the
        # image (ZP fixed at 1, F_pred = measured flux).
        # SPEC: the bright-star supplement (D) is not used here: without a
        # zero point its V magnitudes cannot be converted to image flux.
        ref = self.dets[min(1, nc - 1)]
        xs = np.array([d.x for d in ref])
        ys = np.array([d.y for d in ref])
        n = xs.size
        if n < 10:
            raise HardRefusal("Too few star detections for the in-frame-only fallback.")
        S = np.zeros((n, nc))
        for c in range(nc):
            f, nap, pk = aperture_fluxes(self.img[c], xs, ys, AP_FWHM * self.fwhm_px, "annulus",
                                         fwhm_px=self.fwhm_px)
            sat = np.array([d.saturated for d in ref]) | ~(pk < self.lin[c])
            gv = np.array([d.peak * 2 * math.pi * (max(d.fwhm, 1.0) / 2.3548) ** 2 for d in ref])
            S[:, c] = np.where(sat | ~np.isfinite(f) | (f <= 0), gv, f)
        S = np.maximum(S, 1e-12)
        gpseudo = -2.5 * np.log10(np.sum(S, axis=1))
        table = StarTable(ra=np.zeros(n), dec=np.zeros(n), g=gpseudo, src=np.full(n, "I"))
        self.table = table
        lab, nlab = saturated_regions(self.img, self.lin)
        order = np.argsort(gpseudo)
        self.xs, self.ys, self.rsat = recentre_saturated(lab, nlab, xs, ys, order, geom)
        self.sat_lab = lab
        self.recentred = np.ones(n, bool)
        self.inside = geom.in_frame(self.xs, self.ys)
        self.frame_dist = np.zeros(n)
        self.kappa = np.zeros(n)
        self.S = S
        self.colour = np.full(n, "det", dtype="<U4")
        self.prior_sig = np.full((n, nc), np.nan)
        self.alt_ratio = np.full((n, nc), np.nan)
        R.number("sources", {"positions": ["image detections (in-frame only)"], "spectra": []})
        return self.compute_main(info)


def geom_ok(geom, xs, ys, margin):
    return geom.in_frame(xs, ys, margin) & np.isfinite(xs)


def bayer_absent(kw):
    return not str(getattr(kw, "bayer_pattern", "") or "").strip()


