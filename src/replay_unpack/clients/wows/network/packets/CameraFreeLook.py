# coding=utf-8
import struct

from replay_unpack.core import PrettyPrintObjectMixin


class CameraFreeLook(PrettyPrintObjectMixin):
    def __init__(self, stream):
        (self.locked,) = struct.unpack("?", stream.read(1))
