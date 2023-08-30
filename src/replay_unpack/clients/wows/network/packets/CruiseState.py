# coding=utf-8
import struct

from replay_unpack.core import PrettyPrintObjectMixin


class CruiseState(PrettyPrintObjectMixin):
    def __init__(self, stream):
        (self.key,) = struct.unpack("i", stream.read(4))
        (self.value,) = struct.unpack("i", stream.read(4))
