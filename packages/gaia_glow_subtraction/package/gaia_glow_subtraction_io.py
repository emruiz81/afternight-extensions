# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Adrian Knagg-Baugh
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (GaiaGlowSubtraction for Siril) by Adrian Knagg-Baugh. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/GaiaGlowSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""The AfterNight side of the core's I/O interface, in place of the upstream section 14 (``SirilIO``).

The vendored core only talks to its host through the methods of ``SirilIO``; ``AfterNightIO`` provides them over an
AfterNight image handle, the process's progress object and the package settings. The pixel conventions line up
without a flip: AfterNight keeps a FITS image's rows in storage order and writes WCS cards against those rows, which
is the core's "FITS storage order"; its star finder reports positions with the first pixel's centre at one half, so a
detection's core coordinate is the position minus one half on both axes.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import gaia_glow_subtraction_core as core


MAX_DETECTIONS = 20000
DEFAULT_DATA_DIR_NAME = "gaia_glow_subtraction"

# The one Siril-specific instruction the core gives on a common path, said for AfterNight; the vendored text stays as
# upstream wrote it.
core.LINEAR_WCS_MSG = (
    "The plate solution is linear only (no SIP distortion terms). Re-solve the image with distortion (SIP) terms for "
    "best results; an internal correction fitted on the image's stars is used instead."
)


def default_data_dir():
    """The per-user cache folder for downloaded catalogue pieces, the bright-star table and the last-output record."""

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return str(Path(base) / "AfterNight" / "extensions" / DEFAULT_DATA_DIR_NAME)
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return str(Path(base) / "afternight" / "extensions" / DEFAULT_DATA_DIR_NAME)


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def header_cards(metadata):
    """Return ``[(key, value, raw)]`` for every header card an AfterNight image carries, repeated cards included."""

    cards = _json_value(dict(metadata or {}).get("fits_cards"))
    if isinstance(cards, list) and cards:
        out = []
        for entry in cards:
            if isinstance(entry, dict) and entry.get("key"):
                out.append((str(entry["key"]), str(entry.get("value", "")), entry.get("raw")))
        return out
    header = _json_value(dict(metadata or {}).get("fits_header"))
    if isinstance(header, dict):
        return [(str(key), str(value), None) for key, value in header.items()]
    return []


def _coerce_card_value(text):
    stripped = str(text).strip()
    if stripped in ("T", "F"):
        return stripped == "T"
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return stripped[1:-1].replace("''", "'").rstrip()
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def fits_header(metadata):
    """Build an astropy Header, typed as a FITS file would give it, from an AfterNight image's header cards.

    Each card's raw 80-character record is parsed when the host provides it; otherwise its value text is read as a
    FITS value. Returns None when the image carries no card, which the core refuses as "no FITS header".
    """

    from astropy.io import fits

    cards = header_cards(metadata)
    if not cards:
        return None
    header = fits.Header()
    for key, value, raw in cards:
        card = None
        if raw:
            try:
                card = fits.Card.fromstring(str(raw))
                card.verify("silentfix")
            except Exception:
                card = None
        if card is None:
            try:
                card = fits.Card(key, _coerce_card_value(value))
            except Exception:
                continue
        try:
            header.append(card, end=True)
        except Exception:
            continue
    return header


def _header_get(header, *keys, default=None):
    for key in keys:
        if header is not None and key in header:
            value = header[key]
            if value not in (None, ""):
                return value
    return default


def _number(value, default=0.0):
    try:
        return float(value)
    except TypeError, ValueError:
        return default


def parse_date_obs(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def keywords_from_header(header):
    """The sirilpy FKeywords attributes the core reads, from the matching FITS cards."""

    return SimpleNamespace(
        image_type=str(_header_get(header, "IMAGETYP", default="") or ""),
        stackcnt=int(_number(_header_get(header, "STACKCNT", default=0))),
        livetime=_number(_header_get(header, "LIVETIME", default=0.0)),
        exposure=_number(_header_get(header, "EXPTIME", "EXPOSURE", default=0.0)),
        bayer_pattern=str(_header_get(header, "BAYERPAT", default="") or ""),
        pixel_size_x=_number(_header_get(header, "XPIXSZ", "PIXSIZE1", default=0.0)),
        binning_x=int(_number(_header_get(header, "XBINNING", default=1), 1.0) or 1),
        focal_length=_number(_header_get(header, "FOCALLEN", default=0.0)),
        date_obs=parse_date_obs(_header_get(header, "DATE-OBS", default="")),
        filter=str(_header_get(header, "FILTER", default="") or ""),
        instrume=str(_header_get(header, "INSTRUME", default="") or ""),
        telescop=str(_header_get(header, "TELESCOP", default="") or ""),
    )


def history_from_header(header):
    if header is None or "HISTORY" not in header:
        return []
    return [str(entry) for entry in header["HISTORY"]]


def to_planes(array):
    """Return an AfterNight image array as the core's (channels, height, width)."""

    data = np.asarray(array)
    if data.ndim == 2:
        return data[None]
    if data.ndim == 3:
        return np.moveaxis(data, -1, 0)
    raise ValueError(f"Gaia Glow Subtraction needs a mono or colour image; the image has shape {data.shape}.")


def from_planes(planes, like):
    """Return a (channels, height, width) array in the layout of ``like``."""

    data = np.asarray(planes)
    if np.asarray(like).ndim == 2:
        return data[0]
    return np.moveaxis(data, 0, -1)


def detection_from_star(star, unit_scale, channel):
    """Convert an AfterNight ``find_stars`` record to the core's Detection (astropy 0-based, storage order)."""

    value = star.get if isinstance(star, dict) else (lambda key, default=None: getattr(star, key, default))
    fx = _number(value("fwhm_x", 0.0))
    fy = _number(value("fwhm_y", 0.0))
    fwhm = 0.5 * (fx + fy) if fx > 0 and fy > 0 else max(fx, fy, _number(value("fwhm", 0.0)))
    roundness = (min(fx, fy) / max(fx, fy)) if fx > 0 and fy > 0 else 1.0
    return core.Detection(
        x=_number(value("x", 0.0)) - 0.5,
        y=_number(value("y", 0.0)) - 0.5,
        fwhm=fwhm,
        roundness=roundness,
        peak=_number(value("amplitude", 0.0)) * unit_scale,
        saturated=bool(value("saturated", False)),
        sat=_number(value("saturation", 0.0)) * unit_scale,
        channel=channel,
    )


class AfterNightIO:
    """The ``SirilIO`` interface of the core, over an AfterNight image handle."""

    def __init__(self, image, *, log_fn, progress=None, settings=None, finder=None):
        self.image = image
        self.log_fn = log_fn
        self._progress = progress
        self.settings = dict(settings or {})
        self._finder = finder
        self.findstar_ran = False
        self.written = None
        self.written_label = ""
        self._metadata = None

    # -- logging and progress ---------------------------------------------
    def log(self, msg, kind="info"):
        self.log_fn(str(msg), kind)

    def progress(self, msg, frac):
        if self._progress is not None:
            self._progress.set_text(str(msg))
            self._progress.set_value(100.0 * float(np.clip(frac, 0.0, 1.0)))

    def reset_progress(self):
        pass

    # -- configuration and directories ------------------------------------
    def config(self, group, key):
        if group == "core" and key == "catalogue_gaia_astro":
            return self.settings.get("siril_astro_catalogue") or None
        if group == "core" and key == "catalogue_gaia_photo":
            return self.settings.get("siril_xp_catalogue_dir") or None
        if group == "core" and key == "force_16bit":
            return False
        # Siril's SPCC preferences have no AfterNight counterpart: the core then uses its top-hat channel responses.
        return None

    def userdatadir(self):
        path = Path(self.settings.get("data_dir") or default_data_dir())
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            path = Path(tempfile.gettempdir()) / DEFAULT_DATA_DIR_NAME
            path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def systemdatadir(self):
        return None

    def workdir(self):
        filename = self.filename()
        return os.path.dirname(filename) if filename and os.path.isdir(os.path.dirname(filename)) else None

    # -- image -------------------------------------------------------------
    def _metadata_dict(self):
        if self._metadata is None:
            try:
                self._metadata = dict(getattr(self.image, "metadata", {}) or {})
            except Exception:
                self._metadata = {}
        return self._metadata

    def filename(self):
        return str(self._metadata_dict().get("FILENAME") or "")

    def image_info(self):
        header = fits_header(self._metadata_dict())
        data = np.asarray(self.image.to_numpy())
        nc = 1 if data.ndim == 2 else int(data.shape[-1])
        bitpix = {np.dtype(np.uint8): 8, np.dtype(np.uint16): 16, np.dtype(np.float32): -32}.get(data.dtype)
        return {
            "filename": self.filename(),
            "header": header,
            "header_str": header.tostring(sep="\n") if header is not None else "",
            "keywords": keywords_from_header(header),
            "history": history_from_header(header),
            "icc": None,
            "orig_bitpix": bitpix,
            "nc": nc,
            "stats": [None] * nc,
        }

    def pixel_data(self):
        return to_planes(self.image.to_numpy())

    def detections(self, c, unit_scale, nc, ry):
        """AfterNight's star finder on channel ``c``. ``ry`` (Siril's display flip) does not apply: no flip is needed."""

        del ry
        self.findstar_ran = True
        finder = self._finder
        if finder is None:
            from afternight import registration

            finder = registration.find_stars
        stars = finder(self.image, channel=int(c) if nc > 1 else -1, max_stars=MAX_DETECTIONS) or []
        return [detection_from_star(star, unit_scale, c) for star in stars]

    def write(self, data, label):
        self.written = data
        self.written_label = str(label)

    def current_fingerprint(self):
        return core.image_fingerprint(self.pixel_data(), self.filename())

    def load_image(self, path):
        raise RuntimeError("Gaia Glow Subtraction does not load files into AfterNight.")

    # -- selections and overlays: AfterNight's process window has neither in this port ------------------
    def selection(self):
        return None

    def clear_selection(self):
        return True

    def restore_selection(self, sel):
        return False

    def clear_stars(self):
        return False

    # -- persistent fingerprint (I19) ---------------------------------------
    def _fp_path(self):
        return Path(self.userdatadir()) / "last_output.json"

    def load_last_fingerprint(self):
        try:
            path = self._fp_path()
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def save_last_fingerprint(self, record):
        try:
            path = self._fp_path()
            fd, tmp = tempfile.mkstemp(dir=str(path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
            os.replace(tmp, path)
        except Exception:
            pass
