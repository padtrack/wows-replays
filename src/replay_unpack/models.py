from typing import List, Dict, NamedTuple, Optional, Tuple
from array import array
from collections.abc import MutableSequence
import enum

from packaging.version import Version
from pydantic import BaseModel, Field, PositiveFloat, NonNegativeInt

from replay_unpack.utils import to_lower_camel


class Counts(NamedTuple):
    achievements: int
    chat_messages: int
    deaths: int
    ribbons: int
    stats: int


class Snapshot(NamedTuple):
    current_time: float
    time_left: int
    battle_stage: int
    counts: Counts


class BattleResult(BaseModel):
    winner_team_id: int
    finish_reason: str


class BattleType(BaseModel, alias_generator=to_lower_camel):
    players_per_team: NonNegativeInt
    name: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    teams_count: NonNegativeInt


class BattleLogic(BaseModel):
    battle_result: BattleResult
    battle_type: BattleType
    duration: int
    lose_score: int
    win_score: int


class Relation(enum.Enum):
    SELF = 0
    ALLY = 1
    ENEMY = 2


class CrewSkills(BaseModel, alias_generator=to_lower_camel):
    params_id: NonNegativeInt
    is_in_adaptation: bool
    learned_skills: List[List[NonNegativeInt]]


class ShipConfiguration(BaseModel):
    ship_id: NonNegativeInt
    units: Dict[str, NonNegativeInt]  # modules
    modernization: List[NonNegativeInt]  # upgrades
    exterior: List[NonNegativeInt]  # signals & camo
    auto_supply_state: NonNegativeInt
    color_scheme: List[NonNegativeInt]  # camo & variation
    abilities: List[NonNegativeInt]  # consumables
    ensigns: List[NonNegativeInt]
    boosters: List[NonNegativeInt]
    nation_flag: NonNegativeInt


class Player(BaseModel, alias_generator=to_lower_camel):
    account_id: int = Field(alias="accountDBID")
    avatar_id: Optional[int] = None  # None for bots
    clan_color: int
    clan_id: int = Field(alias="clanID")
    clan_tag: str
    id_: int = Field(alias="id")
    is_bot: bool
    max_health: PositiveFloat
    name: str
    prebattle_id: int  # Division ID, 0 if solo
    realm: Optional[str]  # None for bots
    relation: Relation
    ship_components: Dict[str, str]
    ship_config: ShipConfiguration = Field(alias="ship_config")
    ship_id: int  # entity ID
    ship_params_id: int  # GameParams.data ID
    team_id: int
    # TODO: is team killer isAbuser or ttkStatus?


class Building(BaseModel, alias_generator=to_lower_camel):
    id_: int = Field(alias="id")
    name: str
    params_id: int
    relation: Relation
    team_id: int
    unique_id: int


class Event(BaseModel):
    current_time: float


class Achievement(Event):
    player_id: int
    achievement_id: int


class ChatMessage(Event):
    sender_id: int  # 0, -1 for system messages
    channel_id: str
    message: str


class Death(Event):
    killed_vehicle_id: int
    fragger_vehicle_id: int
    type_death: int
    death_icon: str
    death_name: str


class BuildingState(BaseModel):
    suppressed: bool
    visible: bool = False


# NOTE: not updated after death (Events.dead_buildings)
class BuildingStates(BaseModel, arbitrary_types_allowed=True):
    spawn_time: float
    position: Optional[Tuple[float, float, float]] = None  # NOTE: assumes buildings can't move
    suppressed: MutableSequence[int] = array("B")
    visible: MutableSequence[int] = array("B")


class ConsumableState(BaseModel):
    count: int
    expiry: float = -1

    def is_active_at(self, current_time: float) -> bool:
        if self.expiry < 0:
            return False

        return current_time < self.expiry


class ConsumableStates(BaseModel, arbitrary_types_allowed=True):
    added_at: float
    active: MutableSequence[int] = array("B")
    count: MutableSequence[int] = array("b")  # -1 if infinite charges


class VehicleState(BaseModel):
    health: float
    max_health: float
    regeneration_health: float = 0.0
    regen_crew_hp_limit: float = 0.0
    burning_flags: int = 0
    visibility_flags: int = 0
    appeared: bool = False
    consumables: Dict[int, ConsumableState] = {}


# NOTE: not updated after death (Events.dead_vehicles)
class VehicleStates(BaseModel, arbitrary_types_allowed=True):
    spawn_time: float
    position_diff: MutableSequence[float] = array("f")
    position_counter: MutableSequence[int] = array("I")
    health: MutableSequence[float] = array("f")
    max_health: MutableSequence[float] = array("f")
    regeneration_health: MutableSequence[float] = array("f")
    regen_crew_hp_limit: MutableSequence[float] = array("f")
    burning_flags: MutableSequence[int] = array("I")
    visibility_flags: MutableSequence[int] = array("I")
    appeared: MutableSequence[int] = array("B")
    consumables: Dict[int, ConsumableStates] = {}


class DropData(BaseModel, alias_generator=to_lower_camel):
    appear_time: NonNegativeInt = Field(alias="appear_time")
    params_id: NonNegativeInt
    start_time: NonNegativeInt


class InteractiveZone(BaseModel, arbitrary_types_allowed=True):
    spawn_time: float
    type_: int = Field(alias="type")
    position: Tuple[float, float]  # NOTE: assumes caps can't move
    index: Optional[int]
    team_id: MutableSequence[int] = array("i")
    invader_team: MutableSequence[int] = array("i")
    radius: MutableSequence[float] = array("f")
    progress: MutableSequence[float] = array("f")
    has_invaders: MutableSequence[int] = array("B")
    is_visible: MutableSequence[int] = array("B")


class SmokeScreen(BaseModel, arbitrary_types_allowed=True):
    spawn_time: float
    radius: float
    points: List[Tuple[float, float]]
    bound_left: int
    bound_right: int
    bounds: MutableSequence[int] = array("B")
    despawn_time: Optional[float] = None


class Squadron(BaseModel, arbitrary_types_allowed=True):
    plane_id: int
    owner_id: int
    index: int
    purpose: int
    departures: int
    team_id: int
    params_id: int


class Ward(BaseModel):
    spawn_time: float
    squadron_id: int
    position: Tuple[float, float]
    duration: float
    radius: float
    team_id: int
    owner_id: int
    despawn_time: Optional[float] = None


class Events(BaseModel, arbitrary_types_allowed=True):
    achievements: List[Achievement] = []
    building_states: Dict[int, BuildingStates] = {}
    chat_messages: List[ChatMessage] = []
    dead_buildings: Dict[int, float] = {}
    dead_vehicles: Dict[int, float] = {}
    deaths: List[Death] = []
    focused_by: List[int] = []
    ribbons: List[Dict[str, int]] = []
    stats: List[Dict[str, float]] = []
    score: Dict[int, MutableSequence[int]] = {}
    smokes: Dict[int, SmokeScreen] = {}
    squadron_counter: MutableSequence[int] = array("I")
    squadron_plane_id: MutableSequence[int] = array("Q")
    squadron_position: MutableSequence[float] = array("f")
    vehicle_states: Dict[int, VehicleStates] = {}
    wards: List[Ward] = []
    zones: Dict[int, InteractiveZone] = {}


class ReplayData(BaseModel, arbitrary_types_allowed=True):
    version: Version
    arena_id: NonNegativeInt
    map_: str = Field(alias="map", min_length=1)
    battle_logic: BattleLogic
    game_mode: str
    owner_account_id: int
    owner_avatar_id: int
    owner_id: int
    owner_vehicle_id: int
    crew_skills: Dict[int, CrewSkills]
    drops: Dict[int, DropData]
    players: Dict[int, Player]
    buildings: Dict[int, Building]
    squadrons: Dict[int, Squadron]
    snapshots: List[Snapshot]
    events: Events
