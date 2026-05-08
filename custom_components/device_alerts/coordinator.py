from __future__ import annotations

import datetime
import fnmatch
import json
import logging
import re
from pathlib import Path

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_UUID_RE = re.compile(r"^[\w\-.:]+$")
UPDATE_INTERVAL = datetime.timedelta(minutes=30)


def validate_key(value: str | None, max_len: int = 128) -> str | None:
    if not value or len(value) > max_len:
        return None
    if not _UUID_RE.match(str(value)):
        return None
    return value


class DeviceAlertsCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.entry = entry
        self._snooze_file = Path(hass.config.path(f"custom_components/{DOMAIN}/snooze.json"))

    # ---- File I/O (blocking, run in executor) ---------------------------------

    def _read_snooze_sync(self) -> dict:
        try:
            return json.loads(self._snooze_file.read_text())
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError):
            _LOGGER.warning("device_alerts: corrupt snooze file — treating as empty")
            return {}

    def _write_snooze_sync(self, data: dict) -> None:
        try:
            self._snooze_file.write_text(json.dumps(data))
        except OSError as exc:
            _LOGGER.error("device_alerts: could not write snooze file: %s", exc)

    # ---- Config reading -------------------------------------------------------

    def _get_helper(self, entity_id: str, default: str = "") -> str:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return default
        return state.state

    def _read_config(self) -> dict:
        raw_patterns  = self._get_helper("input_text.device_alerts_ignore_patterns")
        raw_uuids     = self._get_helper("input_text.device_alerts_ignore_uuids")
        raw_overrides = self._get_helper("input_text.device_alerts_battery_thresholds_override", "{}")
        raw_mobile    = self._get_helper("input_text.device_alerts_notify_mobile_services")
        gate_entity   = self._get_helper("input_text.device_alerts_notify_gate_entity").strip() or None
        smtp_service  = self._get_helper("input_text.device_alerts_smtp_service").strip() or None
        raw_smtp_tgts = self._get_helper("input_text.device_alerts_smtp_targets")

        try:
            global_thresh = int(float(
                self._get_helper("input_number.device_alerts_battery_threshold", "20")
            ))
        except (ValueError, TypeError):
            global_thresh = 20

        try:
            threshold_overrides = json.loads(raw_overrides)
            if not isinstance(threshold_overrides, dict):
                threshold_overrides = {}
        except (json.JSONDecodeError, ValueError):
            _LOGGER.warning("device_alerts: invalid JSON in battery_thresholds_override — ignoring")
            threshold_overrides = {}

        return {
            "ignore_patterns":     [p.strip() for p in raw_patterns.split(",") if p.strip()],
            "ignore_uuids":        {u.strip() for u in raw_uuids.split(",") if u.strip()},
            "global_threshold":    global_thresh,
            "threshold_overrides": threshold_overrides,
            "mobile_services":     [s.strip() for s in raw_mobile.split(",") if s.strip()],
            "gate_entity":         gate_entity,
            "smtp_service":        smtp_service,
            "smtp_targets":        [t.strip() for t in raw_smtp_tgts.split(",") if t.strip()],
        }

    # ---- Snooze helpers -------------------------------------------------------

    @staticmethod
    def _is_snoozed(key: str, snoozed_map: dict) -> tuple[bool, str | None]:
        if key not in snoozed_map:
            return False, None
        try:
            until = datetime.datetime.fromisoformat(snoozed_map[key])
        except (ValueError, TypeError):
            return False, None
        now = datetime.datetime.now(tz=until.tzinfo)
        if until > now:
            return True, snoozed_map[key]
        return False, None

    @staticmethod
    def _clean_expired_snoozes(snoozed_map: dict) -> dict:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        cleaned = {}
        for k, v in snoozed_map.items():
            try:
                if datetime.datetime.fromisoformat(v) > now:
                    cleaned[k] = v
            except (ValueError, TypeError):
                pass
        return cleaned

    # ---- Core check logic (runs in event loop — no blocking I/O) -------------

    def _run_checks(self, snoozed: dict) -> tuple[dict, dict, dict]:
        er = entity_registry.async_get(self.hass)
        dr = device_registry.async_get(self.hass)
        cfg = self._read_config()
        ignore_uuids        = cfg["ignore_uuids"]
        ignore_patterns     = cfg["ignore_patterns"]
        global_threshold    = cfg["global_threshold"]
        threshold_overrides = cfg["threshold_overrides"]

        # Unavailability check
        unavail_devices: dict = {}
        for device_id in dr.devices:
            if device_id in ignore_uuids:
                continue
            entries = entity_registry.async_entries_for_device(er, device_id)
            relevant = [
                e for e in entries
                if e.disabled_by is None
                and e.entity_category is None
                and not any(fnmatch.fnmatch(e.entity_id, p) for p in ignore_patterns)
            ]
            if not relevant:
                continue
            if all(self.hass.states.is_state(e.entity_id, STATE_UNAVAILABLE) for e in relevant):
                device = dr.async_get(device_id)
                state_objects = [self.hass.states.get(e.entity_id) for e in relevant]
                since = min(
                    (s.last_changed for s in state_objects if s is not None),
                    default=None,
                )
                _, snooze_until = self._is_snoozed(device_id, snoozed)
                unavail_devices[device_id] = {
                    "name":          device.name if device else device_id,
                    "manufacturer":  device.manufacturer if device else None,
                    "model":         device.model if device else None,
                    "since":         str(since),
                    "snoozed_until": snooze_until,
                }

        # Battery check
        low_battery: dict = {}
        for state_obj in self.hass.states.async_all():
            entity_id = state_obj.entity_id
            attrs = state_obj.attributes
            if attrs.get("device_class") != "battery":
                continue
            if any(fnmatch.fnmatch(entity_id, p) for p in ignore_patterns):
                continue
            er_entry = er.async_get(entity_id)
            if er_entry and er_entry.device_id in ignore_uuids:
                continue
            if er_entry and er_entry.device_id in unavail_devices:
                continue
            threshold = threshold_overrides.get(entity_id, global_threshold)
            domain = entity_id.split(".")[0]
            flagged = False
            if domain == "sensor":
                try:
                    flagged = float(state_obj.state) < threshold
                except (ValueError, TypeError):
                    pass
            elif domain == "binary_sensor":
                flagged = state_obj.state == "on"
            if flagged:
                _, snooze_until = self._is_snoozed(entity_id, snoozed)
                low_battery[entity_id] = {
                    "name":          attrs.get("friendly_name", entity_id),
                    "state":         state_obj.state,
                    "threshold":     threshold,
                    "snoozed_until": snooze_until,
                }

        cleaned_snoozed = self._clean_expired_snoozes(snoozed)
        return unavail_devices, low_battery, cleaned_snoozed

    # ---- Notifications --------------------------------------------------------

    async def _async_send_notifications(self, title: str, message: str, cfg: dict) -> None:
        gate = cfg["gate_entity"]
        if gate:
            gate_state = self.hass.states.get(gate)
            if not gate_state or gate_state.state != "on":
                return
        for svc in cfg["mobile_services"]:
            await self.hass.services.async_call(
                "notify", svc, {"title": title, "message": message}, blocking=False
            )
        if cfg["smtp_service"] and cfg["smtp_targets"]:
            await self.hass.services.async_call(
                "notify", cfg["smtp_service"],
                {"title": title, "message": message, "data": {"target": cfg["smtp_targets"]}},
                blocking=False,
            )

    async def _async_fire_notifications(self, unavail: dict, battery: dict, cfg: dict) -> None:
        active_unavail = {k: v for k, v in unavail.items() if not v["snoozed_until"]}
        if active_unavail:
            lines = []
            for info in active_unavail.values():
                desc = info["name"] or "(unknown)"
                if info.get("model"):
                    desc += f" ({info['model']})"
                lines.append(f"- {desc} — since {(info['since'] or '?')[:19]}")
            msg = "\n".join(lines)
            await self._async_send_notifications("Unavailable Devices", msg, cfg)
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": "device_availability_warning",
                 "title": "Unavailable Devices", "message": msg},
                blocking=False,
            )
        else:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": "device_availability_warning"},
                blocking=False,
            )

        active_battery = {k: v for k, v in battery.items() if not v["snoozed_until"]}
        if active_battery:
            lines = []
            for info in active_battery.values():
                state_str = "unavailable" if info["state"] == STATE_UNAVAILABLE else f"{info['state']}%"
                lines.append(f"- {info['name']}: {state_str} (threshold {info['threshold']}%)")
            msg = "\n".join(lines)
            await self._async_send_notifications("Low Battery Alert", msg, cfg)
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": "low_battery_alert",
                 "title": "Low Battery Alert", "message": msg},
                blocking=False,
            )
        else:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": "low_battery_alert"},
                blocking=False,
            )

    async def _async_update_snooze_dropdown(self, unavail: dict, battery: dict) -> None:
        if self.hass.states.get("input_select.device_alerts_snooze_target") is None:
            return
        options = ["(none)"]
        for device_id, info in unavail.items():
            options.append(f"unavail::{device_id}::{info['name']}")
        for entity_id, info in battery.items():
            options.append(f"battery::{entity_id}::{info['name']}")
        try:
            await self.hass.services.async_call(
                "input_select", "set_options",
                {"entity_id": "input_select.device_alerts_snooze_target", "options": options},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    # ---- Main update ----------------------------------------------------------

    async def _async_update_data(self) -> dict:
        try:
            snoozed = await self.hass.async_add_executor_job(self._read_snooze_sync)
            unavail, battery, cleaned_snoozed = self._run_checks(snoozed)
            await self.hass.async_add_executor_job(self._write_snooze_sync, cleaned_snoozed)
            await self._async_update_snooze_dropdown(unavail, battery)
            cfg = self._read_config()
            await self._async_fire_notifications(unavail, battery, cfg)
            return {"unavail": unavail, "battery": battery}
        except Exception as exc:
            raise UpdateFailed(f"device_alerts check failed: {exc}") from exc

    # ---- Z-Wave dead node ----------------------------------------------------

    async def async_handle_zwave_dead(self, entity_id: str, new_state) -> None:
        cfg = self._read_config()
        device_name = (
            new_state.attributes.get("friendly_name", entity_id) if new_state else entity_id
        )
        await self._async_send_notifications(
            "Z-Wave Device Dead",
            (f"Device offline: {device_name}\n"
             "Node status changed to 'dead'.\n"
             "Check battery and Z-Wave connection."),
            cfg,
        )

    # ---- Service handlers ----------------------------------------------------

    async def async_add_snooze(self) -> None:
        target_state = self.hass.states.get("input_select.device_alerts_snooze_target")
        until_state  = self.hass.states.get("input_datetime.device_alerts_snooze_until")
        target = target_state.state if target_state else None
        until  = until_state.state if until_state else None
        if not target or target == "(none)" or not until:
            _LOGGER.warning("device_alerts_add_snooze: no target or until date selected")
            return
        parts = target.split("::", 2)
        if len(parts) < 2:
            _LOGGER.warning("device_alerts_add_snooze: unexpected target format: %s", target)
            return
        key = validate_key(parts[1])
        if not key:
            _LOGGER.warning("device_alerts_add_snooze: invalid key: %r", parts[1])
            return
        snoozed_map = await self.hass.async_add_executor_job(self._read_snooze_sync)
        dt = datetime.datetime.fromisoformat(until.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        snoozed_map[key] = dt.isoformat()
        await self.hass.async_add_executor_job(self._write_snooze_sync, snoozed_map)
        _LOGGER.info("device_alerts: snoozed %s until %s", key, dt.isoformat())
        await self.async_refresh()

    async def async_clear_snooze(self) -> None:
        state = self.hass.states.get("input_select.device_alerts_snooze_target")
        if not state or state.state == "(none)":
            return
        parts = state.state.split("::", 2)
        if len(parts) < 2:
            return
        key = validate_key(parts[1])
        if not key:
            return
        snoozed_map = await self.hass.async_add_executor_job(self._read_snooze_sync)
        snoozed_map.pop(key, None)
        await self.hass.async_add_executor_job(self._write_snooze_sync, snoozed_map)
        _LOGGER.info("device_alerts: cleared snooze for %s", key)
        await self.async_refresh()

    async def async_quick_snooze(self, uuid: str | None, days: int = 7) -> None:
        uuid = validate_key(uuid)
        if not uuid:
            _LOGGER.warning("device_alerts_quick_snooze: no valid uuid provided")
            return
        days = max(1, min(365, int(days)))
        until = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=days)
        snoozed_map = await self.hass.async_add_executor_job(self._read_snooze_sync)
        snoozed_map[uuid] = until.isoformat()
        await self.hass.async_add_executor_job(self._write_snooze_sync, snoozed_map)
        _LOGGER.info("device_alerts: quick-snoozed %s until %s", uuid, until.isoformat())
        await self.async_refresh()

    async def async_quick_ignore(self, uuid: str | None) -> None:
        uuid = validate_key(uuid)
        if not uuid:
            _LOGGER.warning("device_alerts_quick_ignore: no valid uuid provided")
            return
        current_state = self.hass.states.get("input_text.device_alerts_ignore_uuids")
        current = current_state.state if current_state and current_state.state not in ("unknown", "unavailable") else ""
        existing = {u.strip() for u in current.split(",") if u.strip()}
        if uuid in existing:
            _LOGGER.info("device_alerts: %s already ignored", uuid)
            return
        existing.add(uuid)
        new_value = ",".join(sorted(existing))
        if len(new_value) > 1000:
            _LOGGER.warning("device_alerts_quick_ignore: ignore_uuids would exceed 1000 chars — skipping")
            return
        await self.hass.services.async_call(
            "input_text", "set_value",
            {"entity_id": "input_text.device_alerts_ignore_uuids", "value": new_value},
            blocking=True,
        )
        _LOGGER.info("device_alerts: quick-ignored %s", uuid)
        await self.async_refresh()

    async def async_set_battery_threshold(self, entity_id: str | None, threshold) -> None:
        entity_id = validate_key(entity_id)
        if not entity_id or "." not in entity_id:
            _LOGGER.warning("set_battery_threshold: invalid entity_id")
            return
        current_state = self.hass.states.get("input_text.device_alerts_battery_thresholds_override")
        raw = (current_state.state
               if current_state and current_state.state not in ("unknown", "unavailable", "")
               else "{}")
        try:
            overrides = json.loads(raw)
            if not isinstance(overrides, dict):
                overrides = {}
        except (json.JSONDecodeError, ValueError):
            overrides = {}
        try:
            thresh = max(0, min(100, int(threshold))) if threshold is not None else 0
        except (ValueError, TypeError):
            thresh = 0
        if thresh <= 0:
            overrides.pop(entity_id, None)
            _LOGGER.info("set_battery_threshold: reset %s to global default", entity_id)
        else:
            overrides[entity_id] = thresh
            _LOGGER.info("set_battery_threshold: set %s to %d%%", entity_id, thresh)
        new_value = json.dumps(overrides)
        if len(new_value) > 1000:
            _LOGGER.warning("set_battery_threshold: overrides JSON would exceed 1000 chars — skipping")
            return
        await self.hass.services.async_call(
            "input_text", "set_value",
            {"entity_id": "input_text.device_alerts_battery_thresholds_override", "value": new_value},
            blocking=True,
        )
        await self.async_refresh()
