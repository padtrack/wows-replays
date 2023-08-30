from typing import Any, Dict, List, Optional, Tuple, Union
import array
import io
import json
import os
import struct

from packaging.version import Version
import packaging.version

from replay_unpack.core import IBattleController
from replay_unpack.core.entity import Entity
from replay_unpack.core.entity_def.data_types.nested_types import PyFixedDict, PyFixedList
from replay_unpack.models import (
    Achievement,
    BattleLogic,
    BattleResult,
    Building,
    BuildingState,
    BuildingStates,
    ChatMessage,
    ConsumableState,
    ConsumableStates,
    Counts,
    CrewSkills,
    Death,
    DropData,
    Events,
    InteractiveZone,
    Player,
    Relation,
    ReplayData,
    ShipConfiguration,
    SmokeScreen,
    Snapshot,
    Squadron,
    VehicleState,
    VehicleStates,
    Ward,
)
from replay_unpack.utils import restricted_loads, to_snake_case, unpack_plane_id, unpack_values


BATTLE_RESULTS_ALIASES = {
    "interactions": "CLIENT_VEH_INTERACTION_DETAILS",
    "buildingInteractions": "CLIENT_BUILDING_INTERACTION_DETAILS",
}
POSITION_AND_YAW_PATTERN = (
    (-2500.0, 2500.0, 11),
    (-2500.0, 2500.0, 11),
    (-3.141592753589793, 3.141592753589793, 8),
)
DAMAGE_STATS_TYPES = ["ENEMY", "ALLY", "SPOT", "AGRO"]
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class PlayersInfo:
    def __init__(self):
        self.players = {}

    def update(self, constants: Dict[str, Any], data: List[Tuple[Any]], player_type: str):
        if player_type == "BUILDING":
            property_map = {
                str(index): value
                for index, value in enumerate(
                    constants["SHARED_DATA_CONSTANTS"]["CLIENT_BUILDING_DATA"]
                )
            }
        else:
            property_map = constants[f"{player_type.upper()}_NUM_MEMBER_MAP"]

        for player_data in data:
            player_info = {property_map[str(key)]: val for key, val in player_data}
            player_info["player_type"] = player_type
            self.players.setdefault(player_info["id"], {}).update(player_info)


class BattleController(IBattleController):
    METHOD_CALLS = {
        "Avatar": [
            "capturedAsAGoal",
            "onAchievementEarned",
            "onArenaStateReceived",
            "onChatMessage",
            "onGameRoomStateChanged",
            "onNewPlayerSpawnedInBattle",
            "receiveDamageStat",
            "receiveVehicleDeath",
            "receive_addMinimapSquadron",
            "receive_removeMinimapSquadron",
            "receive_squadronDamage",
            "receive_updateMinimapSquadron",
            "receive_wardAdded",
            "receive_wardRemoved",
            "startDissapearing",  # [sic]
            "updateMinimapVisionInfo",
        ],
        "Vehicle": [
            "setConsumables",
            "consumableUsed",
        ],
    }
    PROPERTY_CHANGES = {
        "BattleLogic": ["state"],
        "Building": ["isAlive", "isSuppressed"],
        "InteractiveZone": ["componentsState"],
        "Vehicle": [
            "burningFlags",
            "crewModifiersCompactParams",
            "health",
            "isAlive",
            "maxHealth",
            "regenCrewHpLimit",
            "regenerationHealth",
            "uiEnabled",
            "visibilityFlags",
        ],
    }
    NESTED_PROPERTY_CHANGES = {
        "Avatar": ["privateVehicleState.ribbons"],
        "BattleLogic": ["state.missions.teamsScore", "state.drop.data"],
        "SmokeScreen": ["points"],
    }

    def __init__(self, version: str, period: float = 0.5):
        self.constants = self.load_constants(version)
        self.ribbon_names = [
            key[7:] for key in self.constants["PLAYER_FULL_RESULTS"] if key.startswith("RIBBON_")
        ]

        self.period: float = period
        self._current_time: float = 0.0
        self._previous_bar: float = 0.0

        self._arena_id: Optional[int] = None
        self._battle_logic_id: Optional[int] = None
        self._battle_results: Optional[Dict[str, Any]] = None
        self._building_state: Dict[int, BuildingState] = {}
        self._buildings: Dict[int, Building] = {}
        self._crew_skills: Dict[int, CrewSkills] = {}
        self._drops: Dict[int, DropData] = {}
        self._entities: Dict[int, Entity] = {}
        self._events: Events = Events()
        self._focused_by: int = 0
        self._map: Optional[str] = None
        self._owner_account_id: Optional[int] = None
        self._owner_avatar_id: Optional[int] = None
        self._owner_id: Optional[int] = None
        self._owner_vehicle_id: Optional[int] = None
        self._players: Dict[int, Player] = {}
        self._players_info: PlayersInfo = PlayersInfo()
        self._ribbons: Dict[str, int] = {}
        self._score: Dict[int, int] = {}
        self._ship_owned_by: Dict[int, int] = {}
        self._snapshots: List[Snapshot] = []
        self._squadrons: Dict[int, Squadron] = {}
        self._squadron_damage: float = 0.0
        self._squadron_positions: Dict[int, Optional[Tuple[float, float]]] = {}
        self._stats: Dict[str, Dict[int, float]] = {stat: {} for stat in DAMAGE_STATS_TYPES}
        self._vehicle_state: Dict[int, VehicleState] = {}
        self._version: Optional[Version] = None

        for entity_type, methods in self.METHOD_CALLS.items():
            for method in methods:
                Entity.subscribe_method_call(
                    entity_type, method, getattr(self, to_snake_case(method))
                )

        for entity_type, properties in self.PROPERTY_CHANGES.items():
            for property in properties:
                Entity.subscribe_property_change(
                    entity_type,
                    property,
                    getattr(self, entity_type.lower() + "_" + to_snake_case(property)),
                )

        for entity_type, properties in self.NESTED_PROPERTY_CHANGES.items():
            for property in properties:
                name = property[property.rfind(".") + 1 :]
                Entity.subscribe_nested_property_change(
                    entity_type,
                    property,
                    getattr(self, entity_type.lower() + "_" + to_snake_case(name)),
                )

    def load_constants(self, version: str) -> Dict[str, Any]:
        with open(os.path.join(BASE_DIR, "versions", version, "constants.json")) as fp:
            return json.load(fp)

    def get_data(self) -> ReplayData:
        if self.period > 0:  # force snapshot to handle sub-period events
            self.take_snapshot()

        self._events.squadron_counter.append(len(self._events.squadron_plane_id))

        raw = self.battle_logic.properties["client"]
        battle_logic = BattleLogic(
            battle_result=BattleResult(
                winner_team_id=raw["battleResult"]["winnerTeamId"],
                finish_reason=self.constants["FINISH_REASONS"][
                    str(raw["battleResult"]["finishReason"])
                ],
            ),
            battle_type=self.constants["BATTLE_TYPES"][str(raw["battleType"])],
            duration=raw["duration"],
            lose_score=raw["state"]["missions"]["teamLoseScore"],
            win_score=raw["state"]["missions"]["teamWinScore"],
        )

        assert self._battle_results is not None, "Replay is incomplete."

        return ReplayData(
            version=self._version,  # type: ignore
            arena_id=self._arena_id,  # type: ignore
            map=self._map,  # type: ignore
            battle_logic=battle_logic,
            game_mode=self.constants["GAME_MODES"][
                str(self._battle_results["common"]["game_mode"])
            ],
            owner_account_id=self._owner_account_id,  # type: ignore
            owner_avatar_id=self._owner_avatar_id,  # type: ignore
            owner_id=self._owner_id,  # type: ignore
            owner_vehicle_id=self._owner_vehicle_id,  # type: ignore
            crew_skills=self._crew_skills,
            drops=self._drops,
            players=self._players,
            buildings=self._buildings,
            squadrons=self._squadrons,
            snapshots=self._snapshots,
            events=self._events,
        )

    @property
    def current_time(self):
        return self._current_time

    @current_time.setter
    def current_time(self, value: float):
        if self.period > 0 and self._previous_bar + self.period < value:
            self.take_snapshot()
            self._previous_bar += self.period

        self._current_time = value

    def take_snapshot(self):
        current_time: float = self.current_time
        time_left: int = self.battle_logic.properties["client"]["timeLeft"]
        battle_stage: int = self.battle_logic.properties["client"]["battleStage"]

        if battle_stage == -1:
            return

        self._snapshots.append(
            Snapshot(
                current_time=current_time,
                time_left=time_left,
                battle_stage=battle_stage,
                counts=Counts(
                    len(self._events.achievements),
                    len(self._events.chat_messages),
                    len(self._events.chat_messages),
                    len(self._events.ribbons),
                    len(self._stats),
                ),
            )
        )

        self._events.focused_by.append(self._focused_by)

        for team_id, score in self._score.items():
            self._events.score[team_id].append(score)

        for entity_id, state in self._building_state.items():
            if entity_id in self._events.dead_buildings:
                continue

            b = self._events.building_states[entity_id]
            b.suppressed.append(state.suppressed)
            b.visible.append(state.visible)

        for entity_id, state in self._vehicle_state.items():
            if entity_id in self._events.dead_vehicles:
                continue

            v = self._events.vehicle_states[entity_id]
            v.position_counter.append(len(v.position_diff))
            v.health.append(state.health)
            v.max_health.append(state.max_health)
            v.regeneration_health.append(state.regeneration_health)
            v.regen_crew_hp_limit.append(state.regen_crew_hp_limit)
            v.burning_flags.append(state.burning_flags)
            v.visibility_flags.append(state.visibility_flags)
            v.appeared.append(state.appeared)

            for type_id, consumable_state in state.consumables.items():
                c = v.consumables[type_id]
                c.active.append(consumable_state.is_active_at(self.current_time))
                c.count.append(consumable_state.count)

        for entity_id, zone in self._events.zones.items():
            raw = self._entities[entity_id].properties["client"]

            zone.team_id.append(raw["teamId"])
            zone.radius.append(raw["radius"])

            cl = raw["componentsState"]["captureLogic"]
            if cl:
                zone.invader_team.append(cl["invaderTeam"])
                zone.progress.append(cl["progress"])
                zone.has_invaders.append(cl["hasInvaders"])
                zone.is_visible.append(cl["isVisible"])

        for smoke in self._events.smokes.values():
            smoke.bounds.append(smoke.bound_left)
            smoke.bounds.append(smoke.bound_right)

        self._events.squadron_counter.append(len(self._events.squadron_plane_id))
        for plane_id, position in self._squadron_positions.items():
            if position:
                self._events.squadron_plane_id.append(plane_id)
                self._events.squadron_position.append(position[0])
                self._events.squadron_position.append(position[1])

    @property
    def owner(self):
        return self._players_info.players[self._owner_id]

    @property
    def battle_logic(self):
        if self._battle_logic_id:
            return self.entities[self._battle_logic_id]

        entity_id, entity = next(
            (eid, e) for eid, e in self._entities.items() if e.get_name() == "BattleLogic"
        )
        self._battle_logic_id = entity_id
        return entity

    @property
    def entities(self):
        return self._entities

    def create_entity(self, entity: Entity):
        self._entities[entity.id] = entity

        if entity.get_name() == "SmokeScreen":
            raw = entity.properties["client"]
            self._events.smokes[entity.id] = SmokeScreen(
                spawn_time=self.current_time,
                radius=raw["radius"],
                points=raw["points"],
                bound_left=0,
                bound_right=len(raw["points"]) - 1,
            )

    def destroy_entity(self, entity: Entity):
        del self.entities[entity.id]

    def leave_entity(self, entity_id: int):
        if entity_id in self._events.smokes:
            self._events.smokes[entity_id].despawn_time = self.current_time

    @property
    def map(self):
        return self._map

    @map.setter
    def map(self, value: str):
        self._map = value.removeprefix("spaces/")

    @property
    def owner_vehicle_id(self):
        return self._owner_vehicle_id

    @owner_vehicle_id.setter
    def owner_vehicle_id(self, value: int):
        self._owner_vehicle_id = value

    @property
    def battle_results(self):
        return self._battle_results

    @battle_results.setter
    def battle_results(self, value: Dict[str, Any]):
        assert value["arenaUniqueID"] == self._arena_id
        self._owner_account_id = value["accountDBID"]
        self._battle_results = {
            "private_data": {
                key: (
                    {subkey: subval for subkey, subval in zip(self.constants[key.upper()], val)}
                    if key.upper() in self.constants
                    else val
                )
                for key, val in zip(
                    self.constants["PLAYER_PRIVATE_RESULTS"], value["privateDataList"]
                )
            },
            "common": {
                key: val for key, val in zip(self.constants["COMMON_RESULTS"], value["commonList"])
            },
            "players": {
                player_id: {
                    key: (
                        {
                            subkey: subval
                            for subkey, subval in zip(
                                self.constants[BATTLE_RESULTS_ALIASES[key]], val
                            )
                        }
                        if key in BATTLE_RESULTS_ALIASES
                        else val
                    )
                    for key, val in zip(self.constants["CLIENT_PUBLIC_RESULTS"], values)
                }
                for player_id, values in value["playersPublicInfo"].items()
            },
        }

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value: str):
        self._version = packaging.version.parse(value.replace(",", "."))

    def on_player_enter_world(self, entity_id: int):
        self._owner_avatar_id = entity_id

    # Helper functions

    def unpack_ship_config(self, dump: str) -> Dict[str, Any]:
        data = {}

        with io.BytesIO(dump.encode("latin1")) as fp:
            # while chunk := fp.read(4):
            #     print(struct.unpack("<L", chunk)[0])
            # print()
            # return

            def read(num=None):
                if num is None:
                    num = struct.unpack("<L", fp.read(4))[0]

                for _ in range(num):
                    yield struct.unpack("<L", fp.read(4))[0]

            ship_id_length = next(read(1))
            assert ship_id_length == 1
            data["ship_id"] = next(read(1))

            payload_length = next(read(1))
            assert payload_length * 4 == len(fp.getbuffer()) - fp.tell()
            units_length = next(read(1))
            assert units_length == len(self.constants["UNIT_TYPES"])

            data["units"] = {
                unit: slot
                for unit, slot in zip(self.constants["UNIT_TYPES"], read(units_length))
                if slot
            }
            data["modernization"] = [slot for slot in read()]
            data["exterior"] = [slot for slot in read()]
            data["auto_supply_state"] = next(read(1))
            data["color_scheme"] = [slot for slot in read()]

            a = next(read(1))
            b = next(read(1))

            # assume that all ability IDs are larger than 64
            if b > 64:  # no unknown byte
                data["abilities"] = [b] + [slot for slot in read(a - 1)]
            else:  # unknown byte is a
                data["abilities"] = [slot for slot in read(b)]

            data["ensigns"] = [slot for slot in read()]
            data["boosters"] = [slot for slot in read()]
            _ = next(read(1))  # EcoboostSlots.dumpAutoBuyInfo()
            data["nation_flag"] = next(read(1))

        return data

    def update_players(self):
        for player in self._players_info.players.values():
            if player["player_type"] == "OBSERVER":
                continue

            if (
                player.get("avatarId") == self._owner_avatar_id
                or player.get("id") == self._owner_avatar_id
            ):
                relation = Relation(0)
            elif player["teamId"] == self.owner["teamId"]:
                relation = Relation(1)
            else:
                relation = Relation(2)

            if player["player_type"] in ["PLAYER", "BOT"]:
                if player["id"] not in self._players:
                    self._vehicle_state[player["shipId"]] = VehicleState(
                        health=player["maxHealth"], max_health=player["maxHealth"]
                    )
                    self._events.vehicle_states[player["shipId"]] = VehicleStates(
                        spawn_time=self.current_time
                    )

                ship_config = self.unpack_ship_config(player["shipConfigDump"])
                self._players[player["id"]] = Player(
                    **player, relation=relation, ship_config=ShipConfiguration(**ship_config)
                )
                self._ship_owned_by[player["shipId"]] = player["id"]
            if player["player_type"] == "BUILDING":
                if player["id"] not in self._buildings:
                    self._building_state[player["id"]] = BuildingState(
                        suppressed=player["isSuppressed"]
                    )
                    self._events.building_states[player["id"]] = BuildingStates(
                        spawn_time=self.current_time
                    )

                self._buildings[player["id"]] = Building(
                    **player,
                    relation=relation,
                )

    def update_stats(self):
        data = {
            stat: total
            for stat, targets in self._stats.items()
            if (total := sum(amount for amount in targets.values())) > 0
        }
        data["PLANE"] = self._squadron_damage

        self._events.stats.append(data)

    # Avatar

    def captured_as_a_goal(self, avatar: Entity, numFocusingEnemies: int):
        self._focused_by = numFocusingEnemies

    def on_arena_state_received(
        self,
        avatar: Entity,
        arenaUniqueId: int,
        teamBuildTypeId: int,
        preBattlesInfo: bytes,
        playersStates: bytes,
        botsStates: bytes,
        observersState: bytes,
        buildingsInfo: bytes,
    ):
        self._arena_id = arenaUniqueId

        for data, player_type in [
            (playersStates, "PLAYER"),
            (botsStates, "BOT"),
            (observersState, "OBSERVER"),
            (buildingsInfo, "BUILDING"),
        ]:
            self._players_info.update(
                self.constants, restricted_loads(data, encoding="latin1"), player_type
            )

        assert self._owner_avatar_id is not None
        self._owner_id = next(
            _id
            for _id, player in self._players_info.players.items()
            if player.get("avatarId") == self._owner_avatar_id
        )

        self.update_players()

    def on_game_room_state_changed(
        self, avatar: Entity, playersData: bytes, botsData: bytes, observersData: bytes
    ):
        for data, player_type in [
            (playersData, "PLAYER"),
            (botsData, "BOT"),
            (observersData, "OBSERVER"),
        ]:
            self._players_info.update(
                self.constants, restricted_loads(data, encoding="latin1"), player_type
            )

    def on_new_player_spawned_in_battle(
        self, avatar: Entity, playersData: bytes, botsData: bytes, observersData: bytes
    ):
        for data, player_type in [
            (playersData, "PLAYER"),
            (botsData, "BOT"),
            (observersData, "OBSERVER"),
        ]:
            self._players_info.update(
                self.constants, restricted_loads(data, encoding="latin1"), player_type
            )

        self.update_players()

    def on_achievement_earned(self, avatar: Entity, playerId: int, achievementId: int):
        # if playerId != self._owner_id:
        #     return

        self._events.achievements.append(
            Achievement(
                current_time=self.current_time,
                player_id=playerId,
                achievement_id=achievementId,
            )
        )

    def on_chat_message(
        self, avatar: Entity, senderId: int, channelId: str, message: str, extraData: str
    ):
        self._events.chat_messages.append(
            ChatMessage(
                current_time=self.current_time,
                sender_id=senderId,
                channel_id=channelId,
                message=message,
            )
        )

    def receive_vehicle_death(
        self, avatar: Entity, killedVehicleId: int, fraggerVehicleId: int, typeDeath: int
    ):
        death_reason = self.constants["DEATH_REASONS"][str(typeDeath)]
        self._events.deaths.append(
            Death(
                current_time=self.current_time,
                killed_vehicle_id=killedVehicleId,
                fragger_vehicle_id=fraggerVehicleId,
                type_death=typeDeath,
                death_icon=death_reason["icon"],
                death_name=death_reason["name"],
            )
        )

    def avatar_ribbons(self, avatar: Entity, value: Union[PyFixedList, PyFixedDict]):
        # this is a private property, but make sure anyways
        if avatar.id != self._owner_avatar_id:
            return

        def update(*states):
            for state in states:
                self._ribbons[self.ribbon_names[state["ribbonId"]]] = state["count"]

            self._events.ribbons.append(self._ribbons.copy())

        if isinstance(value, PyFixedList):
            update(*value)
        else:
            update(value)

    def receive_damage_stat(self, avatar: Entity, pickledData: bytes):
        for (target, stat), (_, amount) in restricted_loads(pickledData).items():
            self._stats[DAMAGE_STATS_TYPES[stat]][target] = amount

        self.update_stats()

    def receive_squadron_damage(self, avatar: Entity, sqId: int, health: int, modifiers: int):
        self._squadron_damage += health
        self.update_stats()

    def update_minimap_vision_info(self, avatar: Entity, shipsMinimapDiff, buildingsMinimapDiff):
        for ship_diff in shipsMinimapDiff:
            x, y, yaw = unpack_values(ship_diff["packedData"], POSITION_AND_YAW_PATTERN)
            vehicle_id = ship_diff["vehicleID"]

            if (x == -2500) and (y == -2500):
                self._vehicle_state[vehicle_id].visibility_flags = 0
                self._vehicle_state[vehicle_id].appeared = False
            else:
                self._events.vehicle_states[vehicle_id].position_diff.extend((x, y, yaw))

        for building_diff in buildingsMinimapDiff:
            x, y, yaw = unpack_values(building_diff["packedData"], POSITION_AND_YAW_PATTERN)
            building_id = building_diff["vehicleID"]

            if (x == -2500) and (y == -2500):
                self._building_state[building_id].visible = False
            else:
                self._events.building_states[building_id].position = (x, y, yaw)
                self._building_state[building_id].visible = True

    def receive_ward_added(
        self,
        avatar: Entity,
        sqId: int,
        position: Tuple[float, float, float],
        duration: float,
        radius: float,
        teamId: int,
        ownerId: int,
    ):
        self._events.wards.append(
            Ward(
                spawn_time=self.current_time,
                squadron_id=sqId,
                position=(position[0], position[2]),
                duration=duration,
                radius=radius,
                team_id=teamId,
                owner_id=ownerId,
            )
        )

    def receive_ward_removed(self, avatar: Entity, sqId):
        ward = next(w for w in self._events.wards if sqId == w.squadron_id)
        ward.despawn_time = self.current_time

    def start_dissapearing(self, avatar: Entity, shipId: int):
        self._vehicle_state[shipId].appeared = False

    def receive_add_minimap_squadron(
        self,
        avatar: Entity,
        planeID: int,
        teamID: int,
        paramsID: int,
        position: Tuple[float, float],
        airOnly: bool,
    ):
        owner_id, index, purpose, departures = unpack_plane_id(planeID)
        self._squadrons[planeID] = Squadron(
            plane_id=planeID,
            owner_id=owner_id,
            index=index,
            purpose=purpose,
            departures=departures,
            team_id=teamID,
            params_id=paramsID,
        )
        self._squadron_positions[planeID] = position

    def receive_remove_minimap_squadron(self, avatar: Entity, planeID: int):
        self._squadron_positions[planeID] = None

    def receive_update_minimap_squadron(
        self, avatar: Entity, planeID: int, position: Tuple[float, float]
    ):
        self._squadron_positions[planeID] = position

    # BattleLogic

    def battlelogic_state(self, battle_logic: Entity, value):
        assert self.current_time == 0.0

        for data in value["missions"]["teamsScore"]:
            team_id = data["teamId"]

            if team_id not in self._events.score:
                self._events.score[team_id] = array.array("h")

            self._score[team_id] = data["score"]

    def battlelogic_teams_score(self, battle_logic: Entity, value: Dict[str, int]):
        self._score[value["teamId"]] = value["score"]

    def battlelogic_data(self, battle_logic: Entity, value: List[Dict[str, Any]]):
        for data in value:
            if data["zoneId"] in self._drops:
                continue

            self._drops[data["zoneId"]] = DropData(
                appear_time=self.battle_logic.properties["client"]["timeLeft"], **data
            )

    # Building

    def building_is_alive(self, building: Entity, value: bool):
        if not value:
            self._events.dead_vehicles[building.id] = self.current_time

    def building_is_suppressed(self, building: Entity, value: int):
        self._building_state[building.id].suppressed = bool(value)

    # InteractiveZone

    def interactivezone_components_state(self, interactive_zone: Entity, value: bool):
        raw = interactive_zone.properties["client"]
        self._events.zones[interactive_zone.id] = InteractiveZone(
            spawn_time=self.current_time,
            type=raw["type"],
            position=(interactive_zone.position[0], interactive_zone.position[1]),
            index=raw["componentsState"]["controlPoint"]["index"]
            if raw["componentsState"]["controlPoint"]
            else None,
        )

    # SmokeScreen

    def smokescreen_points(self, smoke_screen: Entity, value: List[Tuple[float, float]]):
        s = self._events.smokes[smoke_screen.id]

        for point in value:
            if point not in s.points:
                s.points.append(point)

        s.bound_left = s.points.index(value[0])
        s.bound_right = s.points.index(value[-1])

    # Vehicle

    def set_consumables(self, vehicle: Entity, dumpStates: bytes):
        states = self._events.vehicle_states[vehicle.id].consumables

        for type_id, consumable in restricted_loads(dumpStates):
            state = self._vehicle_state[vehicle.id].consumables

            if type_id not in state:
                state[type_id] = ConsumableState(count=consumable[1])
                states[type_id] = ConsumableStates(added_at=self.current_time)
            else:
                state[type_id].count = consumable[1]

    def consumable_used(self, vehicle: Entity, consumableType: int, workTimeLeft: float):
        c = self._vehicle_state[vehicle.id].consumables[consumableType]
        c.expiry = self.current_time + workTimeLeft
        c.count -= 1

    def vehicle_burning_flags(self, vehicle: Entity, value: int):
        self._vehicle_state[vehicle.id].burning_flags = value

    def vehicle_crew_modifiers_compact_params(self, vehicle: Entity, value: Dict[str, Any]):
        self._crew_skills[vehicle.id] = CrewSkills(**value)

    def vehicle_health(self, vehicle: Entity, value: float):
        self._vehicle_state[vehicle.id].health = value

    def vehicle_is_alive(self, vehicle: Entity, value: bool):
        if not value:
            self._events.dead_vehicles[vehicle.id] = self.current_time

    def vehicle_max_health(self, vehicle: Entity, value: float):
        self._vehicle_state[vehicle.id].max_health = value

    def vehicle_regeneration_health(self, vehicle: Entity, value: float):
        self._vehicle_state[vehicle.id].regeneration_health = value

    def vehicle_regen_crew_hp_limit(self, vehicle: Entity, value: float):
        self._vehicle_state[vehicle.id].regen_crew_hp_limit = value

    def vehicle_ui_enabled(self, vehicle: Entity, value: bool):
        assert value == 1
        self._vehicle_state[vehicle.id].appeared = True

    def vehicle_visibility_flags(self, vehicle: Entity, value: int):
        self._vehicle_state[vehicle.id].visibility_flags = value
