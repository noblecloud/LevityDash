# https://github.com/RCJacH/color_systems/blob/master/color_systems/generators/cubehelix.py

import math

import numpy as np


MAX_SHAPE_SIZE = 65565


def _clip(v, minimum, maximum, dtype=float):
    v = dtype(v)
    min_ = min(v, maximum if maximum is not None else v)
    return max(minimum if minimum is not None else v, min_)


def _make_tuple(v, default=(None, None)):
    try:
        iter(v)
    except TypeError:
        return [x if x is not None else v for x in default]
    else:
        return list(v)


def _set_input_range(v, minimum=None, maximum=None):
    iterable = _make_tuple(v)
    return [_clip(x, minimum, maximum) for x in iterable]


TRANSFORM_MATRIX = ((
    -0.14861, 1.78277,
), (
    -0.29227, -0.90649,
), (
    1.97249, 0.0,
))


def _rotation_vector(angle):
    return np.array([np.cos(angle), np.sin(angle)])


def _get_color_list(fract, amp, angle):
    tm = np.einsum('jk, ij->ik', _rotation_vector(angle), TRANSFORM_MATRIX)
    transformed_colors = (fract + amp * tm).T
    return np.clip(transformed_colors, 0.0, 1.0)


def _float_to_rgb(color_list):
    return (255 * color_list).astype(np.uint8)


def _rgb_to_hex(rgb_list):
    return [
        '#{0}'.format(''.join('{0:#0{1}X}'.format(y, 4)[2:] for y in x))
        for x in rgb_list
    ]


def cubehelix(
    shape,
    hue=0,
    rotations=0.0,
    saturation=1,
    lightness=(0, 1),
    gamma=1.0,
    reverse=False,
    dtype='int',
):
    """Generate a list of RGB values with the cubehelix color scheme.

    Cubehelix is intended to create color schemes spanning from black
    to white, traversing through red, green, and blue using a tapered
    helix in the colour cube with increasing perceived intensity. See
    http: // www.mrao.cam.ac.uk / ~dag / CUBEHELIX/

    Parameters
    ----------
    shape: int
        The number of colors to return
    hue: float, optional
        The central hue at the middle of the scheme, ranging from 0 to 3
        with 0 being red, 1 being green, and 2 being blue, by default 0.
    rotations: float, tuple, optional
        Deviation from the central hue with rotations of the helix.
        Typically - 1.5 to 1.5. -1.0 is one blue -> green -> red cycle.
        Defaults to 0 being monochrome. Can be negative.
    saturation: float, tuple, optional
        The saturation range of the scheme, by default 1
    lightness: float, tuple, optional
        The lightness range of the scheme, by default(0, 1).
    gamma: float, optional
        Emphasis of low or high intensity, by default 1.0
    reverse: bool, optional
        Return color list reversed.
    dtype: {'int', 'float', 'hex'}, optional
        Controls the format of the generated list. 'int' returns
        tuples of(r, g, b) with value 0 to 255. 'float' returns tuples
        of(r, g, b) with value 0 to 1. 'hex' returns strings in the
        format of '#RRGGBB'

    Returns
    -------
    A list of colors in a choosen format.
    """
    rots = _make_tuple(rotations, default=(0, None))
    rots[0] = -rots[0]
    rotation = sum(rots)
    hue = (hue + hue * rots[0] + 1) % 3
    shape = _clip(shape, 1, MAX_SHAPE_SIZE, int)

    # Define transform scalars
    fract = np.linspace(*_set_input_range(lightness, 0, 2), shape)
    angle = 2.0 * math.pi * (hue / 3.0 + rotation * fract + 1)
    fract **= gamma

    satar = np.linspace(*_set_input_range(saturation, 0, 2), shape)
    amp = satar * fract * (1.0 - fract) / 2.0

    color_list = _get_color_list(fract, amp, angle)

    if dtype != 'float':
        color_list = _float_to_rgb(color_list)
        if dtype == 'hex':
            color_list = _rgb_to_hex(color_list)

    return color_list[::-1] if reverse else color_list
