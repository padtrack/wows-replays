from typing import Any, BinaryIO, Dict, List, Optional
import io
import json
import struct
import zlib

from Cryptodome.Cipher import Blowfish
import packaging.version
from pydantic import BaseModel

from replay_unpack.clients.wows.player import ReplayPlayer
from replay_unpack.models import ReplayData


# https://github.com/landaire/wowsreplay/blob/master/docs/ReverseEngineeringNotes.md#finding-the-decryption-key
BLOWFISH_KEY = b"\x29\xB7\xC9\x09\x38\x3F\x84\x88\xFA\x98\xEC\x4E\x13\x19\x79\xFB"
FILE_SIGNATURE = b"\x12\x32\x34\x11"


class Replay(BaseModel):
    arena_info: Dict[Any, Any]
    extras: List[bytes]
    data: ReplayData


class ReplayParser:
    def __init__(self, fp: BinaryIO, strict: bool = False):
        self.fp: BinaryIO = fp
        self.strict: bool = strict

    def parse(self, period: float) -> Replay:
        if self.fp.read(4) != FILE_SIGNATURE:
            raise ValueError("Replay does not match expected signature")

        (count,) = struct.unpack("i", self.fp.read(4))
        (block_size,) = struct.unpack("i", self.fp.read(4))

        arena_info = json.loads(self.fp.read(block_size))

        extras = [self.fp.read(struct.unpack("i", self.fp.read(4))[0]) for _ in range(count - 1)]
        # 1: unknown, empty?
        # 2: owner database id & arena id encoded in utf-8 (ex. "503379282.7586554612222861")

        (raw_size,) = struct.unpack("i", self.fp.read(4))
        (compressed_size,) = struct.unpack("i", self.fp.read(4))

        blowfish = Blowfish.new(BLOWFISH_KEY, Blowfish.MODE_ECB)
        buffer = io.BytesIO()
        previous_block: Optional[int] = None
        encrypted = self.fp.read()

        for index in range(0, len(encrypted), 8):
            chunk = encrypted[index : index + 8]

            (decrypted_block,) = struct.unpack("q", blowfish.decrypt(chunk))
            if previous_block:
                decrypted_block ^= previous_block
            previous_block = decrypted_block

            buffer.write(struct.pack("q", decrypted_block))

        compressed = buffer.getvalue()
        assert len(compressed) == compressed_size
        raw = zlib.decompress(compressed)
        assert len(raw) == raw_size

        version = packaging.version.parse(arena_info["clientVersionFromXml"].replace(",", "."))
        player = ReplayPlayer(version, period)
        player.play(raw, self.strict)
        data = player.get_data()

        # TODO: wrap this up, log
        from pympler import asizeof

        print(asizeof.asizeof(data))

        return Replay(arena_info=arena_info, extras=extras, data=data)
