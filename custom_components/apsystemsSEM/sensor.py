"""The read-only sensors for the APmeter SEM local API integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType, StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LOGGER
from .coordinator import ApMeterConfigEntry, ApMeterData, ApMeterDataCoordinator, ApMeterOutputData
from .entity import ApSystemsEntity
from .sem_tcp import SemFrame


@dataclass(frozen=True, kw_only=True)
class ApMeterSensorDescription(SensorEntityDescription):
    """Describes APmeter sensor entity."""

    value_fn: Callable[[ApMeterOutputData], float | None]
    # Value from a port-3333 frame; used instead of value_fn while frames are fresh.
    tcp_value_fn: Callable[[SemFrame], float] | None = None


SENSORS: tuple[ApMeterSensorDescription, ...] = (
    ApMeterSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.p,
        tcp_value_fn=lambda f: round(f.p, 1),
    ),
    ApMeterSensorDescription(
        key="power_l1",
        translation_key="power_l1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.p1,
        tcp_value_fn=lambda f: round(f.l1, 1),
    ),
    ApMeterSensorDescription(
        key="power_l2",
        translation_key="power_l2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.p2,
        tcp_value_fn=lambda f: round(f.l2, 1),
    ),
    ApMeterSensorDescription(
        key="power_l3",
        translation_key="power_l3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.p3,
        tcp_value_fn=lambda f: round(f.l3, 1),
    ),
    ApMeterSensorDescription(
        key="reactive_power",
        translation_key="reactive_power",
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.q,
    ),
    ApMeterSensorDescription(
        key="reactive_power_l1",
        translation_key="reactive_power_l1",
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.q1,
    ),
    ApMeterSensorDescription(
        key="reactive_power_l2",
        translation_key="reactive_power_l2",
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.q2,
    ),
    ApMeterSensorDescription(
        key="reactive_power_l3",
        translation_key="reactive_power_l3",
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.q3,
    ),
    ApMeterSensorDescription(
        key="apparent_power",
        translation_key="apparent_power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.s,
    ),
    ApMeterSensorDescription(
        key="apparent_power_l1",
        translation_key="apparent_power_l1",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.s1,
    ),
    ApMeterSensorDescription(
        key="apparent_power_l2",
        translation_key="apparent_power_l2",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.s2,
    ),
    ApMeterSensorDescription(
        key="apparent_power_l3",
        translation_key="apparent_power_l3",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.s3,
    ),
    ApMeterSensorDescription(
        key="voltage_l1",
        translation_key="voltage_l1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.v1,
    ),
    ApMeterSensorDescription(
        key="voltage_l2",
        translation_key="voltage_l2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.v2,
    ),
    ApMeterSensorDescription(
        key="voltage_l3",
        translation_key="voltage_l3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.v3,
    ),
    ApMeterSensorDescription(
        key="current_l1",
        translation_key="current_l1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.c1,
    ),
    ApMeterSensorDescription(
        key="current_l2",
        translation_key="current_l2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.c2,
    ),
    ApMeterSensorDescription(
        key="current_l3",
        translation_key="current_l3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.c3,
    ),
    ApMeterSensorDescription(
        key="import_energy",
        translation_key="import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.iE,
    ),
    ApMeterSensorDescription(
        key="import_energy_l1",
        translation_key="import_energy_l1",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.iE1,
    ),
    ApMeterSensorDescription(
        key="import_energy_l2",
        translation_key="import_energy_l2",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.iE2,
    ),
    ApMeterSensorDescription(
        key="import_energy_l3",
        translation_key="import_energy_l3",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.iE3,
    ),
    ApMeterSensorDescription(
        key="export_energy",
        translation_key="export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.eE,
    ),
    ApMeterSensorDescription(
        key="export_energy_l1",
        translation_key="export_energy_l1",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.eE1,
    ),
    ApMeterSensorDescription(
        key="export_energy_l2",
        translation_key="export_energy_l2",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.eE2,
    ),
    ApMeterSensorDescription(
        key="export_energy_l3",
        translation_key="export_energy_l3",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.eE3,
    ),
    ApMeterSensorDescription(
        key="power_factor",
        translation_key="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.pf,
    ),
    ApMeterSensorDescription(
        key="power_factor_l1",
        translation_key="power_factor_l1",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.pf1,
    ),
    ApMeterSensorDescription(
        key="power_factor_l2",
        translation_key="power_factor_l2",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.pf2,
    ),
    ApMeterSensorDescription(
        key="power_factor_l3",
        translation_key="power_factor_l3",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.pf3,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ApMeterConfigEntry,
    add_entities: AddConfigEntryEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    entities = [
        ApMeterSensorWithDescription(data=config_entry.runtime_data, entity_description=desc)
        for desc in SENSORS
    ]
    add_entities(entities)


class ApMeterSensorWithDescription(
    CoordinatorEntity[ApMeterDataCoordinator], ApSystemsEntity, SensorEntity
):
    """Base sensor to be used with description."""

    entity_description: ApMeterSensorDescription
    _attr_has_entity_name = True

    def __init__(self, data: ApMeterData, entity_description: ApMeterSensorDescription) -> None:
        super().__init__(data.coordinator)
        ApSystemsEntity.__init__(self, data)
        self.entity_description = entity_description
        self._attr_unique_id = f"{data.device_id}_{entity_description.key}"
        self._attr_force_update = entity_description.device_class is SensorDeviceClass.ENERGY
        self._tcp_coordinator = data.tcp_coordinator if entity_description.tcp_value_fn else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._tcp_coordinator is not None:
            self.async_on_remove(
                self._tcp_coordinator.async_add_listener(self._handle_coordinator_update)
            )

    def _fresh_frame(self) -> SemFrame | None:
        if self._tcp_coordinator is None:
            return None
        return self._tcp_coordinator.fresh_frame()

    @property
    def native_value(self) -> StateType:
        frame = self._fresh_frame()
        if frame is not None and self.entity_description.tcp_value_fn is not None:
            return self.entity_description.tcp_value_fn(frame)
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data.output_data)

    @property
    def available(self) -> bool:
        if self._fresh_frame() is not None:
            return True
        if self.coordinator.data is None:
            return False
        return getattr(self.coordinator, "is_data_available", True)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self._tcp_coordinator is None:
            return None
        return {"source": "tcp" if self._fresh_frame() is not None else "http"}
