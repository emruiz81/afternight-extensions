"""A synthetic linear, plate-solved star field with glowing bright stars, and a star finder in AfterNight's format."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


SIZE = 768
SCALE_ARCSEC = 2.0
CENTRE = (83.82, -5.39)
STAR_COUNT = 200
BRIGHT_COUNT = 6
GLOW_AMPLITUDE = 1e-3
GLOW_CORE_PX = 8.0
NOISE = 5e-4
G_ZERO_POINT = 8.0


def wcs_cards(size=SIZE, scale_arcsec=SCALE_ARCSEC, centre=CENTRE, solved=True):
    """FITS cards of a stacked light with a north-up TAN solution, as AfterNight's sidecar lists them."""

    from astropy.io import fits

    header = fits.Header()
    if solved:
        cdelt = scale_arcsec / 3600.0
        header["CTYPE1"] = "RA---TAN"
        header["CTYPE2"] = "DEC--TAN"
        header["CRVAL1"] = centre[0]
        header["CRVAL2"] = centre[1]
        header["CRPIX1"] = (size + 1) / 2.0
        header["CRPIX2"] = (size + 1) / 2.0
        header["CD1_1"] = -cdelt
        header["CD1_2"] = 0.0
        header["CD2_1"] = 0.0
        header["CD2_2"] = cdelt
    header["STACKCNT"] = 40
    header["EXPTIME"] = 120.0
    header["LIVETIME"] = 4800.0
    header["DATE-OBS"] = "2025-12-01T21:30:00"
    header["IMAGETYP"] = "Light"
    header["HISTORY"] = "Stacked in AfterNight"
    return [{"key": card.keyword, "value": str(card.value), "raw": card.image} for card in header.cards]


def stars(seed=4, size=SIZE):
    """Pixel positions and fluxes of the field's stars; the first BRIGHT_COUNT carry most of the glow."""

    rng = np.random.default_rng(seed)
    xs = rng.uniform(12, size - 12, STAR_COUNT)
    ys = rng.uniform(12, size - 12, STAR_COUNT)
    flux = 10 ** rng.uniform(-1.2, 0.5, STAR_COUNT)
    flux[:BRIGHT_COUNT] = 10 ** rng.uniform(1.0, 1.6, BRIGHT_COUNT)
    return xs, ys, flux


def render(seed=4, size=SIZE, glow=True):
    """The field in [0, 1]: a Gaussian core per star and, with ``glow``, a Lorentzian-like aureole, plus sky noise."""

    xs, ys, flux = stars(seed, size)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    image = np.full((size, size), 0.02)
    for x, y, f in zip(xs, ys, flux):
        r2 = (xx - x) ** 2 + (yy - y) ** 2
        image += 0.02 * f * np.exp(-r2 / (2 * 1.4**2))
        if glow:
            image += GLOW_AMPLITUDE * f / (1.0 + r2 / GLOW_CORE_PX**2)
    noise = np.random.default_rng(seed + 100).normal(0.0, NOISE, image.shape)
    return np.clip(image + noise, 0.0, 0.98).astype(np.float32)


def glow_region(seed=4, size=SIZE):
    """Pixels between 8 and 120 px from a bright star: where the glow is and the cores are not."""

    xs, ys, flux = stars(seed, size)
    yy, xx = np.mgrid[0:size, 0:size]
    region = np.zeros((size, size), bool)
    for x, y, f in zip(xs[:BRIGHT_COUNT], ys[:BRIGHT_COUNT], flux[:BRIGHT_COUNT]):
        r = np.hypot(xx - x, yy - y)
        region |= (r > 8) & (r < 120)
    return region


def catalogue(seed=4, size=SIZE):
    """RA, Dec and Gaia G of the field's stars through its WCS, for a fake catalogue."""

    from astropy.io import fits
    from astropy.wcs import WCS

    xs, ys, flux = stars(seed, size)
    header = fits.Header([fits.Card.fromstring(card["raw"]) for card in wcs_cards(size)])
    ra, dec = WCS(header).all_pix2world(xs, ys, 0)
    return ra, dec, -2.5 * np.log10(flux) + G_ZERO_POINT


def find_stars(image, *, channel=-1, max_stars=512, **_unused):
    """A small local-maximum finder that answers like AfterNight's: first pixel centred at one half."""

    data = np.asarray(image.to_numpy() if hasattr(image, "to_numpy") else image, dtype=np.float64)
    plane = data if data.ndim == 2 else data[..., max(channel, 0)]
    if np.issubdtype(np.asarray(image.to_numpy()).dtype, np.integer):
        plane = plane / 65535.0
    background = np.median(plane)
    noise = 1.4826 * np.median(np.abs(plane - background))
    peaks = (plane == ndimage.maximum_filter(plane, size=7)) & (plane > background + 8 * noise)
    labels, count = ndimage.label(peaks)
    found = []
    for y, x in ndimage.center_of_mass(peaks, labels, range(1, count + 1)):
        iy, ix = int(round(y)), int(round(x))
        if not (3 <= iy < plane.shape[0] - 3 and 3 <= ix < plane.shape[1] - 3):
            continue
        box = np.clip(plane[iy - 3 : iy + 4, ix - 3 : ix + 4] - background, 0, None)
        gy, gx = np.mgrid[-3:4, -3:4]
        total = box.sum()
        amplitude = float(box.max())
        scale = 65535.0 if np.issubdtype(np.asarray(image.to_numpy()).dtype, np.integer) else 1.0
        found.append(
            {
                "x": ix + float((box * gx).sum() / total) + 0.5,
                "y": iy + float((box * gy).sum() / total) + 0.5,
                "fwhm_x": 3.3,
                "fwhm_y": 3.3,
                "fwhm": 3.3,
                "amplitude": amplitude * scale,
                "background": float(background) * scale,
                "roundness": 1.0,
                "saturated": bool(plane[iy, ix] >= 0.97),
                "saturation": 0.98 * scale,
                "channel": max(channel, 0),
            }
        )
    found.sort(key=lambda star: -star["amplitude"])
    return found[:max_stars]
