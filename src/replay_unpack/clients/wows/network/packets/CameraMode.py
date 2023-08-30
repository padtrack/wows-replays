# coding=utf-8
import struct

from replay_unpack.core import PrettyPrintObjectMixin


class CameraMode(PrettyPrintObjectMixin):
    def __init__(self, stream):
        (self.mode,) = struct.unpack("i", stream.read(4))
