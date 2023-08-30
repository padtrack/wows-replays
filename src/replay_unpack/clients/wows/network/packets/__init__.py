# coding=utf-8
from replay_unpack.core.packets import (
    BasePlayerCreate,
    EntityControl,
    EntityEnter,
    EntityLeave,
    EntityProperty,
    EntityMethod,
    Position,
    Version,
    NestedProperty,
    Camera,
)
from .CellPlayerCreate import CellPlayerCreate
from .EntityCreate import EntityCreate
from .PlayerEntity import PlayerEntity
from .BattleResults import BattleResults
from .CameraMode import CameraMode
from .Map import Map
from .PlayerPosition import PlayerPosition
from .CameraFreeLook import CameraFreeLook
from .CruiseState import CruiseState

# https://github.com/lkolbly/wows-replays/issues/14
# https://github.com/Monstrofil/replays_unpack/issues/18
# NOTE: 12.6.0 inserted new packet at `0x22`
PACKETS_MAPPING = {
    0x0: BasePlayerCreate,
    0x1: CellPlayerCreate,
    0x2: EntityControl,
    0x3: EntityEnter,
    0x4: EntityLeave,
    0x5: EntityCreate,
    0x7: EntityProperty,
    0x8: EntityMethod,
    0xA: Position,
    # 0xE - emitted frequently and value is consistent across account of replay owner
    # 0xF - emitted once, only 8 bytes
    # 0x10 - emitted twice?, bool
    # 0x13 - emitted once, empty?
    0x16: Version,
    # 0x18 - emitted with 0x25, always 40 * 0x00 followed by a Vec3(-1.0, -1.0, -1.0)?
    # 0x1D - emitted very frequently, fps & ping?
    0x20: PlayerEntity,
    0x22: BattleResults,
    0x23: NestedProperty,
    0x25: Camera,
    # 0x26 - emitted twice?, 10 bytes and first 4 bytes are avatar ID
    0x27: CameraMode,
    0x28: Map,
    # 0x2A - emitted somewhat often, 32 bytes and first 20 are entity ID, 0?, Vector3
    0x2C: PlayerPosition,
    # end of verification of bumped indicies in 12.6.0
    0x2F: CameraFreeLook,
    # 0x30 - emitted twice?, 12 bytes and last 4 bytes are ship IDs
    0x32: CruiseState,
    # 0xFFFFFFFF - emitted at game end, 16 bytes
}
