# VeraLux Starting Point

AfterNight adaptation of VeraLux Starting Point, originally authored by
Riccardo Paterniti as the interactive workflow guide for the VeraLux Siril
script suite.

Starting Point is not registered as a processing process in AfterNight. The
original script is a PyQt6 manual and navigation hub, so the AfterNight port
keeps its workflow guidance as package documentation and leaves execution to
the eight native VeraLux process entries in this suite package.

## Workflow Order

1. VeraLux Nox

   Stage: Linear

   Use first on cropped linear data to reduce broad additive gradients from
   light pollution, vignetting, or uneven background illumination. The
   AfterNight process keeps the original PSF auto-masking, signal-rejection,
   membrane-stiffness, automatic calculation, and optional manual protection
   mask workflow. Press Update Preview to render the selected Nox display:
   input with protection overlay, corrected image, or extracted gradient
   model. When Save Gradient Model is enabled, the model opens as a separate
   image while the active image receives the gradient-removed result.

2. VeraLux Silentium

   Stage: Linear

   Use after gradient cleanup and before stretching to suppress stochastic
   background and chroma noise while protecting real signal. The AfterNight
   first pass exposes the linear noise model, detail guard, shadow smoothness,
   chroma denoise, and highlight protection controls through native parameter
   definitions. Loupe preview and PSF-list masking remain deferred.

3. VeraLux Alchemy

   Stage: Linear

   Use on linear RGB narrowband or dual-band data when Ha and OIII/SII balance
   needs normalization before stretching. Alchemy can normalize weak channels,
   optionally compensate OSC crosstalk through sensor profiles, and prepare
   HOO-style or custom palette mixes while keeping the result linear.

4. VeraLux HyperMetric Stretch

   Stage: Linear to non-linear

   Use as the primary stretch after linear cleanup and color preparation.
   HyperMetric Stretch maps linear signal into a visible non-linear image while
   preserving color-vector relationships and giving control over sky floor,
   color grip, highlight handling, and ready-to-use versus scientific output
   behavior.

5. VeraLux Curves

   Stage: Non-linear

   Use after stretching for tone and color sculpting. The AfterNight first pass
   exposes a native point-curve editor with histogram overlay for RGB/K,
   channel, luminance, chrominance, saturation, and luminance-range limited
   adjustments. The pipette and applied-stage stack UI are deferred to a later
   native UI parity pass.

6. VeraLux Revela

   Stage: Non-linear

   Use on stretched data to reveal local contrast, texture, and larger
   structures without pushing the noise floor. Revela is best used after the
   main stretch and before final color grading, with the mask/shadow controls
   tuned so background remains protected while real structure is enhanced.

7. VeraLux Vectra

   Stage: Non-linear

   Use near the end of the workflow for LCH color-vector grading. Vectra shifts
   hue and saturation selectively around the red, yellow, green, cyan, blue,
   and magenta vectors while preserving luminance and protecting neutral
   shadows and stellar cores. The vector-scope HUD is deferred.

8. VeraLux StarComposer

   Stage: Final

   Use as the final star workflow slice. The current AfterNight process shapes
   the active linear star mask with the upstream rational tone-mapping core.
   Multi-input starless plus star-mask recomposition is available in the core
   as future host UI work, but is not exposed by the first native process UI.

## Practical Flow

For most datasets, use the VeraLux tools in this sequence:

```text
Linear preparation:
  Nox -> Silentium -> Alchemy

Stretching:
  HyperMetric Stretch

Non-linear shaping:
  Curves -> Revela -> Vectra

Final star work:
  StarComposer
```

Nox and Silentium should be used before any stretch. Alchemy also expects
linear RGB data and should feed the stretch. Curves, Revela, and Vectra expect
non-linear data. StarComposer belongs at the end because star profiles and
blend decisions are easiest to judge after the target image is already shaped.

## What Changed From The Siril Guide

- The original PyQt6 Starting Point window is not shipped as an executable
  extension process.
- The original guide's problem-oriented navigation is represented here as
  package documentation instead of a standalone UI.
- References to Siril file loading, undo, process buttons, and PyQt preview
  widgets are adapted to AfterNight's native process-window model.
- Deferred parity items are recorded explicitly so future work can add richer
  help panes, workflow links, or native preview widgets without changing the
  one-package VeraLux installation model.

## Attribution

Original VeraLux Starting Point script Copyright (c) 2025 Riccardo Paterniti.
AfterNight adaptation Copyright (c) 2026 AfterNight contributors. This
documentation is derived from `VeraLux/VeraLux_Starting_Point.py` and is
distributed under GPL-3.0-or-later with the rest of the VeraLux suite port.
