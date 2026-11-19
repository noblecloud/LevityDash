# Sky data

## stars.npy

Every star of visual magnitude 8.0 and brighter (41,486 stars) from the **HYG database** v4.4 (Hipparcos, Yale Bright
Star and Gliese catalogues combined) by David Nash / astronexus, https://codeberg.org/astronexus/hyg, licensed under
the Creative Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0,
https://creativecommons.org/licenses/by-sa/4.0/). This file is an adaptation, under the same licence: the Sun was
dropped and each star was reduced to J2000 right ascension, declination, V magnitude and B-V colour index, quantised
and packed into six bytes (see `catalog()` in `lib/skymap.py`), sorted brightest first.

## milkyway.jpg

The Milky Way from **Deep Star Maps 2020**, NASA/Goddard Space Flight Center Scientific Visualization Studio
(https://svs.gsfc.nasa.gov/4851), built from Gaia DR2 data: ESA/Gaia/DPAC. The 4k galactic-coordinate map
(`milkyway_2020_4k_gal.exr`) was cropped to galactic latitude +50 to -50 degrees and written as an 8-bit JPEG with an
asinh stretch (`MW_STRETCH`, `MW_TOP` in `lib/ui/colors/starsky.py` undo it). NASA imagery is not copyrighted; ESA
Gaia data is used under its terms of use with the credit above.
