from collections import namedtuple
import re
from typing import Any, Tuple

import pickle
import io
import builtins


CAMEL_CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")

PlaneInfo = namedtuple("PlaneInfo", ["avatar_id", "index", "purpose", "departures"])


def to_snake_case(string: str) -> str:
    return CAMEL_CASE_PATTERN.sub("_", string).lower()


def to_camel(string: str) -> str:
    return "".join(word.capitalize() for word in string.split("_"))


def to_lower_camel(string: str) -> str:
    return string[0].lower() + to_camel(string)[1:]


def unpack_plane_id(packed_value: int) -> PlaneInfo:
    values = []
    for bit in [32, 3, 3, 1]:
        value = packed_value & (2**bit - 1)
        packed_value = packed_value >> bit
        values.append(value)
    return PlaneInfo(*values)


def unpack_value(packed_value: int, value_min: float, value_max: float, bits: int) -> float:
    return packed_value / (2**bits - 1) * (abs(value_min) + abs(value_max)) - abs(value_min)


def unpack_values(
    packed_value: int, pack_pattern: Tuple[Tuple[float, float, int], ...]
) -> Tuple[float, ...]:
    values = []
    for i, (min_value, max_value, bits) in enumerate(pack_pattern):
        value = packed_value & (2**bits - 1)

        values.append(unpack_value(value, min_value, max_value, bits))
        packed_value = packed_value >> bits

    # assert packed_value == 0

    return tuple(values)


def restricted_loads(data, **kwargs) -> Any:
    return RestrictedUnpickler(io.BytesIO(data), **kwargs).load()


class CamouflageInfo:
    def __init__(self, *args, **kwargs):
        pass


class PlayerMode:
    def __init__(self, *args, **kwargs):
        pass


class RestrictedUnpickler(pickle.Unpickler):
    SAFE_BUILTINS = {
        "range",
        "complex",
        "set",
        "frozenset",
        "slice",
    }

    def find_class(self, module: str, name: str):
        if module == "builtins" and name in self.SAFE_BUILTINS:
            return getattr(builtins, name)
        elif module == "CamouflageInfo" and name == "CamouflageInfo":
            return CamouflageInfo
        elif module == "PlayerModeDef" and name == "PlayerMode":
            return PlayerMode

        raise pickle.UnpicklingError("global '%s.%s' is forbidden" % (module, name))
