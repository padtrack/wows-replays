# coding=utf-8
import struct
from io import BytesIO

from lxml.etree import _Element

from .base import DataType


class _MathType(DataType):
    STRUCT_TYPE = None

    def __init__(self, header_size=1):
        assert self.STRUCT_TYPE is not None, "STRUCT_TYPE must be defined before initialization"
        super().__init__(header_size=header_size)

    def _get_value_from_stream(self, stream: BytesIO, header_size: int):
        assert self.STRUCT_TYPE is not None, "STRUCT_TYPE undefined while unpacking from stream"
        x = tuple(struct.unpack(self.STRUCT_TYPE, stream.read(self._DATA_SIZE)))
        return x

    def _get_default_value_from_section(self, value: _Element):
        raise RuntimeError(
            f"_get_default_value_from_section for {self.__class__.__name__} is not defined"
        )


class Vector2(_MathType):
    """
    VECTOR2
    — Size(bytes): 8
    Two-dimensional vector of 32-bit floats.
    Represented in Python as a tuple of two numbers (or Math.Vector2).
    """

    STRUCT_TYPE = "ff"
    _DATA_SIZE = 8

    def _get_default_value_from_section(self, value: _Element):
        return list(map(float, value.text.strip().split(" ")))


class Vector3(_MathType):
    """
    VECTOR3
    — Size(bytes): 12
    Three-dimensional vector of 32-bit floats.
    Represented in Python as a tuple of three numbers (or Math.Vector3).
    """

    STRUCT_TYPE = "fff"
    _DATA_SIZE = 12


class Vector4(_MathType):
    """VECTOR4 — Size(bytes): 16
    Four-dimensional vector of 32-bit floats.
    Represented in Python as a tuple of four numbers (or Math.Vector4).
    """

    STRUCT_TYPE = "ffff"
    _DATA_SIZE = 16
