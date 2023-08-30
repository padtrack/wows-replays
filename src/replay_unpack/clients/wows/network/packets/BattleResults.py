# coding=utf-8
import json
import struct

from replay_unpack.core import PrettyPrintObjectMixin


class BattleResults(PrettyPrintObjectMixin):
    def __init__(self, stream):
        (_size,) = struct.unpack("i", stream.read(4))
        self.data = json.loads(stream.read(_size))
