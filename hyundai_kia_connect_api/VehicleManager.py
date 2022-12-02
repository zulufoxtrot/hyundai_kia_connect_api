import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import pytz

from .ApiImpl import ApiImpl, ClimateRequestOptions
from .const import (
    BRAND_HYUNDAI,
    BRAND_KIA,
    BRANDS,
    DOMAIN,
    REGION_CANADA,
    REGION_EUROPE,
    REGION_USA,
    REGIONS,
    VEHICLE_LOCK_ACTION,
    CHARGE_PORT_ACTION,
)
from .HyundaiBlueLinkAPIUSA import HyundaiBlueLinkAPIUSA
from .KiaUvoApiCA import KiaUvoApiCA
from .KiaUvoApiEU import KiaUvoApiEU
from .KiaUvoAPIUSA import KiaUvoAPIUSA
from .Vehicle import Vehicle
from .Token import Token
from .exceptions import VehicleNotFoundError

_LOGGER = logging.getLogger(__name__)


class VehicleManager:
    def __init__(self, region: int, brand: int, username: str, password: str, pin: str, geocode_api_enable: bool = False, geocode_api_use_email: bool = False):
        self.region: int = region
        self.brand: int = brand
        self.username: str = username
        self.password: str = password
        self.geocode_api_enable: bool = geocode_api_enable
        self.geocode_api_use_email: bool = geocode_api_use_email
        self.pin: str = pin

        self.api: ApiImpl = self.get_implementation_by_region_brand(
            self.region, self.brand
        )

        self.vehicles: list[Vehicle] = []

    def initialize(self) -> None:
        self.api.login(self.username, self.password, self.pin)
        vehicles = self.api.get_vehicles()
        for vehicle in vehicles:
            self.vehicles.append(vehicle)
        self.update_all_vehicles_with_cached_state()

    def get_vehicle(self, vehicle_id) -> Vehicle:
        for v in self.vehicles:
            if v.id == vehicle_id:
                return v
        raise VehicleNotFoundError("No vehicle found with this ID")

    def update_all_vehicles_with_cached_state(self) -> None:
        for vehicle in self.vehicles:
            self.update_vehicle_with_cached_state(vehicle)

    def update_vehicle_with_cached_state(self, vehicle: Vehicle) -> None:
        self.api.update_vehicle_with_cached_state(vehicle)
        if self.geocode_api_enable == True:
            self.api.update_geocoded_location(vehicle, self.geocode_api_use_email)

    def check_and_force_update_vehicles(self, force_refresh_interval: int) -> None:
        # Force refresh only if current data is older than the value bassed in seconds.  Otherwise runs a cached update.
        started_at_utc: dt = dt.datetime.now(pytz.utc)
        for vehicle in self.vehicles:
            _LOGGER.debug(
                f"{DOMAIN} - Time differential in seconds: {(started_at_utc - vehicle.last_updated_at).total_seconds()}"
            )
            if (
                started_at_utc - vehicle.last_updated_at
            ).total_seconds() > force_refresh_interval:
                self.force_refresh_vehicle_state(vehicle)
            else:
                self.update_vehicle_with_cached_state(vehicle)

    def force_refresh_all_vehicles_states(self) -> None:
        for vehicle in self.vehicles:
            self.force_refresh_vehicle_state(vehicle)

    def force_refresh_vehicle_state(self, vehicle: Vehicle) -> None:
        self.api.force_refresh_vehicle_state(vehicle)

    def check_and_refresh_token(self) -> bool:
        if self.api.token is None:
            self.initialize()
        if self.api.token.valid_until <= dt.datetime.now(pytz.utc):
            _LOGGER.debug(f"{DOMAIN} - Refresh token expired")
            self.api.login(self.username, self.password)
            self.api.refresh_vehicles(self.vehicles)
            return True
        return False

    def start_climate(self, vehicle_id: str, options: ClimateRequestOptions) -> str:
        return self.api.start_climate(self.get_vehicle(vehicle_id), options)

    def stop_climate(self, vehicle_id: str) -> str:
        return self.api.stop_climate(self.get_vehicle(vehicle_id))

    def lock(self, vehicle_id: str) -> str:
        return self.api.lock_action(self.get_vehicle(vehicle_id), VEHICLE_LOCK_ACTION.LOCK)

    def unlock(self, vehicle_id: str) -> str:
        return self.api.lock_action(self.get_vehicle(vehicle_id), VEHICLE_LOCK_ACTION.UNLOCK)

    def start_charge(self, vehicle_id: str) -> str:
        return self.api.start_charge(self.get_vehicle(vehicle_id))

    def stop_charge(self, vehicle_id: str) -> str:
        return self.api.stop_charge(self.get_vehicle(vehicle_id))

    def set_charge_limits(self, vehicle_id: str, ac: int, dc: int) -> str:
        return self.api.set_charge_limits(self.get_vehicle(vehicle_id), ac, dc)

    def check_action_status(self, vehicle_id: str, action_id: str):
        return self.api.check_action_status(self.get_vehicle(vehicle_id), action_id)

    def open_charge_port(self, vehicle_id: str) -> str:
        return self.api.lock_action(self.get_vehicle(vehicle_id), CHARGE_PORT_ACTION.OPEN)

    def close_charge_port(self, vehicle_id: str) -> str:
        return self.api.lock_action(self.get_vehicle(vehicle_id), CHARGE_PORT_ACTION.CLOSE)

    @staticmethod
    def get_implementation_by_region_brand(region: int, brand: int) -> ApiImpl:
        if REGIONS[region] == REGION_CANADA:
            return KiaUvoApiCA(region, brand)
        elif REGIONS[region] == REGION_EUROPE:
            return KiaUvoApiEU(region, brand)
        elif REGIONS[region] == REGION_USA and BRANDS[brand] == BRAND_HYUNDAI:
            return HyundaiBlueLinkAPIUSA(region, brand)
        elif REGIONS[region] == REGION_USA and BRANDS[brand] == BRAND_KIA:
            return KiaUvoAPIUSA(region, brand)
