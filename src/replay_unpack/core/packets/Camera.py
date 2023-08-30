# coding=utf-8
import struct

from replay_unpack.core import PrettyPrintObjectMixin
from replay_unpack.core.network.types import Vector3


class Camera(PrettyPrintObjectMixin):
    def __init__(self, stream):
        self.unknown1 = Vector3(stream)
        (self.unknown2,) = struct.unpack("f", stream.read(4))

        self.absolute_position = Vector3(stream)
        (self.fov,) = struct.unpack("f", stream.read(4))
        self.position = Vector3(stream)
        self.direction = Vector3(stream)
        self.unknown3 = struct.unpack("f", stream.read(4))
