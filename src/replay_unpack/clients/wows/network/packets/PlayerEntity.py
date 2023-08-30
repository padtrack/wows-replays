# coding=utf-8
import struct

from replay_unpack.core import PrettyPrintObjectMixin


class PlayerEntity(PrettyPrintObjectMixin):
    def __init__(self, stream):
        (self.vehicleId,) = struct.unpack("i", stream.read(4))
