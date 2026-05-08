# Unavailable & Low Battery Alerts

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that monitors your devices for:

- **Unavailable devices** — detects when an entire device goes offline (all relevant entities unavailable), using the HA device registry
- **Low battery** — alerts when battery sensors drop below configurable thresholds, with per-device overrides

Includes snooze management, permanent ignore lists, Z-Wave dead-node push alerts, and optional mobile/email notifications.

---

## Requirements

### HACS Frontend Cards

The included Lovelace dashboard requires these HACS frontend cards:

| Card | HACS Repository |
|---|---|
| `custom:config-template-card` | [iantrich/config-template-card](https://github.com/iantrich/config-template-card) |
| `custom:button-card` | [custom-cards/button-card](https://github.com/custom-cards/button-card) |
| `custom:expander-card` | [Sian-Lee-SA/lovelace-expander-card](https://github.com/Sian-Lee-SA/lovelace-expander-card) |
| `custom:auto-entities` | [thomasloven/lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities) |
| `custom:horizontal-layout` | [thomasloven/lovelace-layout-card](https://github.com/thomasloven/lovelace-layout-card) |

Install all five via HACS → Frontend before adding the dashboard.

---

## Installation

### 1. Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=shanec42&repository=Unavailable-LowBattery-Alerts&category=integration)

Or manually: HACS → Integrations → ⋮ → Custom Repositories → add `shanec42/Unavailable-LowBattery-Alerts` as type **Integration**.

### 2. Add the HA package helpers

Copy `packages/device_alerts.yaml` from this repo into your HA `packages/` directory.

Ensure your `configuration.yaml` includes:
```yaml
homeassistant:
  packages: !include_dir_named packages/
```

Restart HA to create the helper entities.

### 3. Configure the integration

Go to **Settings → Devices & Services → Add Integration** and search for **Unavailable & Low Battery Alerts**.

The setup wizard will ask for (all optional):
- **Mobile notify services** — comma-separated service names, e.g. `mobile_app_my_phone`
- **SMTP notify service** — e.g. `smtp` (leave blank to skip email)
- **SMTP targets** — comma-separated email addresses (only used when SMTP service is set)
- **Notification gate entity** — an entity that must be `on` for notifications to send (e.g. `input_boolean.im_home`); leave blank to always notify

### 4. Add the Lovelace dashboard

Copy the contents of `lovelace/alerts_view.yaml` into a new dashboard view (Raw Configuration Editor).

---

## Configuration

After installation, the **Alerts** dashboard provides:

| Column | Content |
|---|---|
| 1 | Active unavailable devices and low battery alerts with per-device snooze/ignore/threshold controls |
| 2 | Global battery threshold slider, all battery sensors list, snooze management |
| 3 | Ignore patterns, ignored UUIDs, per-device threshold overrides, notification settings |

### Ignore lists
- **Entity glob patterns** — comma-separated, e.g. `*plex*, sensor.my_device_battery`
- **Device UUIDs** — comma-separated HA device UUIDs (found in Settings → Devices → device info)

### Battery thresholds
- Set the **global threshold** (default 20%) via the slider in column 2
- Override per-device via the threshold buttons inside each battery alert's expander, or by editing the JSON map in column 3

### Snooze
- Quick snooze (7 days) from the per-device expander buttons
- Custom snooze date/time via the Snooze Settings pickers

---

## Services

| Service | Description |
|---|---|
| `device_alerts.run_check` | Trigger an immediate check (also available via the Run Check Now button) |
| `device_alerts.quick_snooze` | Snooze an alert for N days (`uuid`, `days` params) |
| `device_alerts.quick_ignore` | Permanently ignore a device by UUID |
| `device_alerts.add_snooze` | Add/update a snooze from the UI pickers |
| `device_alerts.clear_snooze` | Clear a snooze entry |
| `device_alerts.set_battery_threshold` | Set a per-device battery threshold override (`entity_id`, `threshold` params; `threshold=0` resets to global) |

---

## Z-Wave

If you use Z-Wave JS, the integration automatically sends an immediate push notification when any node transitions to `dead` state, bypassing snooze. No additional configuration is needed; this is inert on non-Z-Wave installations.

---

## License

[AGPL-3.0](LICENSE)
