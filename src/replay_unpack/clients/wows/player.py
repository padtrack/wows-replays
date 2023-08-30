import struct
from io import BytesIO

from replay_unpack.core import Entity
from replay_unpack.core.network.player import ControlledPlayerBase
from replay_unpack.models import ReplayData
from .helper import get_definitions, get_controller
from .network.packets import (
    BasePlayerCreate,
    CellPlayerCreate,
    EntityEnter,
    EntityLeave,
    EntityCreate,
    EntityProperty,
    EntityMethod,
    Position,
    Version,
    PlayerEntity,
    BattleResults,
    NestedProperty,
    Map,
    PlayerPosition,
    PACKETS_MAPPING,
)


class ReplayPlayer(ControlledPlayerBase):
    def get_data(self) -> ReplayData:
        return self._battle_controller.get_data()

    def _get_definitions(self):
        v = self.version

        try:
            return get_definitions("_".join(str(n) for n in v.release))
        except RuntimeError:
            return get_definitions(f"{v.major}_{v.minor}_{v.micro}")

    def _get_controller(self):
        v = self.version

        try:
            formatted = "_".join(str(n) for n in v.release)
            return get_controller(formatted)(formatted, self.period)
        except RuntimeError:
            formatted = f"{v.major}_{v.minor}_{v.micro}"
            return get_controller(formatted)(formatted, self.period)

    def _get_packets_mapping(self):
        return PACKETS_MAPPING

    def _process_packet(self, packet, t: float):
        self._battle_controller.current_time = t

        if isinstance(packet, BasePlayerCreate):
            if packet.entityId in self._battle_controller.entities:
                base_player = self._battle_controller.entities[packet.entityId]
            else:
                base_player = Entity(
                    id_=packet.entityId,
                    spec=self._definitions.get_entity_def_by_name("Avatar"),
                )

            io = BytesIO(packet.value.value)
            for index, prop in enumerate(base_player.base_properties):
                base_player.set_base_property(index, io)

            self._battle_controller.create_entity(base_player)
            self._battle_controller.on_player_enter_world(packet.entityId)

        elif isinstance(packet, CellPlayerCreate):
            if packet.entityId in self._battle_controller.entities:
                cell_player = self._battle_controller.entities[packet.entityId]
            else:
                cell_player = Entity(
                    id_=packet.entityId,
                    spec=self._definitions.get_entity_def_by_name("Avatar"),
                )

            io = packet.value.io()
            for index, prop in enumerate(cell_player.client_properties_internal):
                cell_player.set_client_property_internal(index, io)

            self._battle_controller.create_entity(cell_player)

        elif isinstance(packet, EntityEnter):
            self._battle_controller.entities[packet.entityId].is_in_aoi = True

        elif isinstance(packet, EntityLeave):
            self._battle_controller.entities[packet.entityId].is_in_aoi = False
            self._battle_controller.leave_entity(packet.entityId)

        elif isinstance(packet, EntityCreate):
            entity = Entity(
                id_=packet.entityID,
                spec=self._definitions.get_entity_def_by_index(packet.type),
            )

            entity.position = packet.position.x, packet.position.y, packet.position.z

            values = packet.state.io()
            (values_count,) = struct.unpack("B", values.read(1))
            for i in range(values_count):
                k = values.read(1)
                (idx,) = struct.unpack("B", k)
                entity.set_client_property(idx, values)
            assert values.read() == b""
            self._battle_controller.create_entity(entity)

        elif isinstance(packet, EntityProperty):
            entity = self._battle_controller.entities[packet.objectID]
            entity.set_client_property(packet.messageId, packet.data.io())

        elif isinstance(packet, EntityMethod):
            entity = self._battle_controller.entities[packet.entityId]
            entity.call_client_method(packet.messageId, packet.data.io())

        elif isinstance(packet, Position):
            self._battle_controller.entities[packet.entityId].position = packet.position
            self._battle_controller.entities[packet.entityId].yaw = packet.yaw
            self._battle_controller.entities[packet.entityId].pitch = packet.pitch
            self._battle_controller.entities[packet.entityId].roll = packet.roll

        elif isinstance(packet, Version):
            self._battle_controller.version = packet.version

        elif isinstance(packet, PlayerEntity):
            self._battle_controller.owner_vehicle_id = packet.vehicleId

        elif isinstance(packet, BattleResults):
            self._battle_controller.battle_results = packet.data

        elif isinstance(packet, NestedProperty):
            e = self._battle_controller.entities[packet.entity_id]
            packet.read_and_apply(e)

        elif isinstance(packet, Map):
            self._battle_controller.map = packet.name

        elif isinstance(packet, PlayerPosition):
            """
            The first entity ID is the primary position being updated
            Avatar only packets have no position until death and are linked to a vehicle
            After death they have no Vehicle ID and use a position instead
            That is, before death, only the first entity ID has a position
            """

            try:
                if packet.entityId2 != (0,):  # first entity ID gets position of second
                    master_entity = self._battle_controller.entities[packet.entityId2]
                    slave_entity = self._battle_controller.entities[packet.entityId1]

                    slave_entity.position = master_entity.position
                    slave_entity.yaw = master_entity.yaw
                    slave_entity.pitch = master_entity.pitch
                    slave_entity.roll = master_entity.roll

                elif packet.entityId1 and not packet.entityId2:
                    e = self._battle_controller.entities[packet.entityId1]

                    e.position = packet.position
                    e.yaw = packet.yaw
                    e.pitch = packet.pitch
                    e.roll = packet.roll

                else:  # no primary OR secondary entity (impossible?)
                    pass

            except KeyError as e:  # entity/entities not created yet
                pass
