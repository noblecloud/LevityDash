"""TYPE_MAP: hand-written JSON Schema fragments for non-Stateful value types.

Usage:
    from tools.schema_types import build_type_map
    TYPE_MAP = build_type_map()

Each entry maps a Python type to a JSON Schema fragment.  Stateful subclasses
are handled automatically by the generator and don't need an entry here.

Add an entry when you introduce a new non-Stateful value type that appears in
@StateProperty return annotations.
"""

from __future__ import annotations

LENGTH_PATTERN = r"^[\d.]+(px|%|cm|mm|in|pt)?$"


def build_type_map() -> dict[type, dict]:
    """Build the TYPE_MAP after LevityDash imports are ready.

    Must be called *after* ``import LevityDash`` so that real type objects
    (not placeholder stubs) are used as dict keys.
    """
    try:
        from LevityDash.lib.ui.Geometry import (
            Alignment, Direction, DisplayPosition, Geometry,
            DimensionType, LocationFlag,
        )
    except ImportError:
        Alignment = type("Alignment", (), {})
        Direction = type("Direction", (), {})
        DisplayPosition = type("DisplayPosition", (), {})
        Geometry = type("Geometry", (), {})
        DimensionType = type("DimensionType", (), {})
        LocationFlag = type("LocationFlag", (), {})

    try:
        from LevityDash.lib.ui.frontends.PySide.utils import DisplayType
    except ImportError:
        DisplayType = type("DisplayType", (), {})

    try:
        from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import ScaleType
    except ImportError:
        ScaleType = type("ScaleType", (), {})

    try:
        from LevityDash.lib.plugins.categories import CategoryItem
    except ImportError:
        CategoryItem = type("CategoryItem", (), {})

    try:
        from LevityDash.lib.ui.colors import Color
    except ImportError:
        Color = type("Color", (), {})

    try:
        from LevityDash.lib.ui.fonts import FontWeight
    except ImportError:
        FontWeight = type("FontWeight", (), {})

    try:
        from WeatherUnits import Measurement as WeatherMeasurement
        from WeatherUnits import Length as WULength
    except ImportError:
        WeatherMeasurement = type("WeatherMeasurement", (), {})
        WULength = type("WULength", (), {})
    
    try:
        from LevityDash.lib.ui.Geometry import (
            Margins as WUMargins,
            Padding as WUPadding,
            Size as _Size,
        )
    except ImportError:
        WUMargins = type("WUMargins", (), {})
        WUPadding = type("WUPadding", (), {})
        _Size = type("_Size", (), {})

    Length = WULength

    # Also map Size.Height / Size.Width (Geometry subclasses) to the same fragment
    # as Length, since they are length-like types used in Stack properties.
    SizeHeight = getattr(_Size, "Height", type("_SizeHeight", (), {}))
    SizeWidth = getattr(_Size, "Width", type("_SizeWidth", (), {}))

    # Length schema fragment shared by all length-like types
    _length_schema = {
        "oneOf": [
            {"type": "number", "description": "Value in pixels"},
            {
                "type": "string",
                "pattern": LENGTH_PATTERN,
                "description": "Number with optional unit (px, %, cm, mm, in, pt)",
            },
        ]
    }

    # Margins schema fragment
    _margins_schema = {
        "oneOf": [
            {"type": "number", "description": "Uniform margin"},
            {
                "type": "string",
                "pattern": r"^[\d.]+(?:px|%|cm|mm|in|pt)?(?:,\s*[\d.]+(?:px|%|cm|mm|in|pt)?){0,3}$",
                "description": "Comma-separated: top,right,bottom,left",
            },
            {
                "type": "object",
                "properties": {
                    "top": {"$ref": "#/$defs/Length"},
                    "right": {"$ref": "#/$defs/Length"},
                    "bottom": {"$ref": "#/$defs/Length"},
                    "left": {"$ref": "#/$defs/Length"},
                },
                "additionalProperties": False,
            },
        ]
    }

    # Padding schema fragment
    _padding_schema = {
        "oneOf": [
            {"type": "number"},
            {
                "type": "string",
                "pattern": r"^[\d.]+(?:px|%|cm|mm|in|pt)?(?:,\s*[\d.]+(?:px|%|cm|mm|in|pt)?){0,3}$",
            },
            {
                "type": "object",
                "properties": {
                    "top": {"$ref": "#/$defs/Length"},
                    "right": {"$ref": "#/$defs/Length"},
                    "bottom": {"$ref": "#/$defs/Length"},
                    "left": {"$ref": "#/$defs/Length"},
                },
                "additionalProperties": False,
            },
        ]
    }

    return {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},

        Length: _length_schema,
        SizeHeight: _length_schema,
        SizeWidth: _length_schema,

        WUMargins: _margins_schema,
        WUPadding: _padding_schema,

        Geometry: {
            "type": "object",
            "properties": {
                "x": {"$ref": "#/$defs/Length"},
                "y": {"$ref": "#/$defs/Length"},
                "width": {"$ref": "#/$defs/Length"},
                "height": {"$ref": "#/$defs/Length"},
                "fillParent": {"type": "boolean", "description": "Fill parent container"},
            },
            "additionalProperties": False,
        },

        Direction: {
            "type": "string",
            "enum": ["Vertical", "Horizontal"],
            "description": "Layout direction",
        },

        Alignment: {
            "oneOf": [
                {"type": "string", "description": "Text alignment key (e.g. CenterRight, BottomLeft, top_center)"},
                {
                    "type": "object",
                    "properties": {
                        "horizontal": {"type": "string", "enum": ["Left", "Center", "Right", "Justify"]},
                        "vertical": {"type": "string", "enum": ["Top", "Center", "Bottom"]},
                    },
                },
            ],
        },

        ScaleType: {
            "type": "string",
            "enum": ["auto", "fill", "font", "string"],
            "default": "auto",
        },

        DisplayPosition: {
            "type": "string",
            "enum": ["auto", "inline", "below", "hidden", "float-under", "float"],
            "default": "auto",
        },

        DisplayType: {
            "type": "string",
            "enum": ["Text", "Gauge"],
            "default": "Text",
        },

        Color: {
            "oneOf": [
                {"type": "string", "pattern": r"^#?[0-9a-fA-F]{0,6}$",
                 "description": "Hex color (with or without #)"},
                {"type": "string", "description": "Named web color"},
                {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4,
                 "description": "RGBA values (0-255)"},
            ]
        },

        FontWeight: {
            "oneOf": [
                {"type": "string", "enum": ["Thin", "Light", "Normal", "Medium", "SemiBold", "Bold", "Black"]},
                {"type": "integer", "minimum": 100, "maximum": 900},
            ]
        },

        CategoryItem: {
            "type": "string",
            "pattern": r"^[a-zA-Z]+(\.[a-zA-Z0-9_]+)*$",
            "description": "Dotted data key path (e.g. environment.temperature.temperature)",
        },

        LocationFlag: {
            "type": "string",
            "description": "Edge-anchor flags string",
        },

        DimensionType: {
            "type": "string",
            "enum": ["Absolute", "Relative"],
        },

        WeatherMeasurement: {
            "type": "number",
            "description": "Numeric measurement value (unit conversion handled by the schema)",
        },

        bytes: {
            "type": "string",
            "contentEncoding": "base64",
        },
    }


# Convenience singleton: populated once after LevityDash is imported
_TYPE_MAP: dict[type, dict] | None = None


def get_type_map() -> dict[type, dict]:
    """Return the lazily-built TYPE_MAP."""
    global _TYPE_MAP
    if _TYPE_MAP is None:
        _TYPE_MAP = build_type_map()
    return _TYPE_MAP
