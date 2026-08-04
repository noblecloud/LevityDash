"""Govee support code that is not itself a plugin.

Lives outside ``builtin/`` deliberately: ``PluginsLoader.allPlugins()`` scans
that directory with ``pkgutil.iter_modules`` and treats every module it finds
as a plugin candidate, so a helper module sitting there gets imported and
rejected on every startup. Only ``builtin/Govee.py`` is a plugin; the model
table it reads lives here.
"""
from LevityDash.lib.plugins.govee.models import (
	DEFAULT_PRESET, detect_model, ModelPreset, preset_for, PRESETS, trim_payload
)

__all__ = ['ModelPreset', 'PRESETS', 'DEFAULT_PRESET', 'detect_model', 'preset_for', 'trim_payload']
