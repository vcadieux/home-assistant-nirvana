# Nirvana Heat Pump for Home Assistant

[Français](docs/README.fr.md) · English

[![Tests](https://github.com/vcadieux/home-assistant-nirvana/actions/workflows/tests.yml/badge.svg)](https://github.com/vcadieux/home-assistant-nirvana/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/vcadieux/home-assistant-nirvana)](https://github.com/vcadieux/home-assistant-nirvana/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[☕ Buy me a coffee with PayPal](https://www.paypal.com/donate/?business=vcadieux%40vincentcadieux.com&currency_code=CAD)

A custom **cloud integration** for Nirvana pool heat pumps. View water temperature, adjust the target, select pool/spa and control the heat pump from a Home Assistant dashboard.

Version **0.1.1** has been reported working by its first user. Automated tests cover the API client and real Home Assistant platform loading. Compatibility with every Nirvana model and firmware is not yet established.

This is an independent community project, not affiliated with or endorsed by Nirvana or Home Assistant. It requires Internet access and an existing Nirvana app account with a heat pump already linked to it.

## Features

| Entity | Features |
|---|---|
| Thermostat (`climate`) | Water temperature, target adjustment, pool/spa presets, heating/off; cooling when supported |
| Performance (`select`) | Quiet or Eco depending on model, Smart and Boost when allowed |
| Temperature sensors | Water and outside temperature |
| Status sensor | Heating, cooling, idle, defrost, compressor delay, fault or technician control |
| Diagnostics | Cloud connectivity, fault indicator, Wi-Fi signal and last device update |

One device is created per heat pump. Unsupported values appear as unknown. Standalone variable-speed filtration pumps are not supported in this version.

## Install with HACS

Add this as a **custom repository**; it is not in the default HACS catalog.

1. Open **HACS → Custom repositories**.
2. Add `https://github.com/vcadieux/home-assistant-nirvana`, category **Integration**.
3. Find **Nirvana Heat Pump (Cloud)** and download it.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and search for **Nirvana Heat Pump (Cloud)**.
6. Sign in with the account used in the Nirvana app. Enter an MFA code if prompted.

## Manual installation

1. Download `nirvana-cloud-0.1.1.zip` from the [latest release](https://github.com/vcadieux/home-assistant-nirvana/releases/latest).
2. Extract it and copy `custom_components/nirvana_cloud` into your Home Assistant configuration directory:

   ```text
   /config/custom_components/nirvana_cloud/manifest.json
   /config/custom_components/nirvana_cloud/__init__.py
   ```

3. Restart Home Assistant, then add **Nirvana Heat Pump (Cloud)** through **Settings → Devices & services**.

`/config` is the usual Home Assistant OS path. For Container/Core, use the directory containing `configuration.yaml`. Home Assistant installs the pinned `pycognito` dependency automatically. No YAML configuration or local heat-pump IP address is needed.

## Dashboard and controls

Add a built-in **Thermostat** card and select the integration's `climate` entity. Use its target temperature and heating/off controls. The **Pool / Spa** preset chooses which target to control; changing a preset enables that mode. Use the separate **Performance** entity for Quiet/Eco/Smart/Boost.

[examples/dashboard.yaml](examples/dashboard.yaml) includes a thermostat, status entities and Pool/Spa/Off buttons. Replace its example entity IDs with those created on your installation; names depend on device names and your language. No third-party cards are required.

```yaml
action: climate.set_temperature
target:
  entity_id: climate.piscine
data:
  temperature: 28
```

Temperatures in Home Assistant actions use your Home Assistant unit system. The integration converts to the device's native C/F and rounds to the nearest whole native degree. It respects device limits and the app's caps: pool 35 °C / 95 °F, spa 40 °C / 104 °F.

## Behavior and account data

- Polls the cloud every **30 seconds**; configure 15–300 seconds in the integration options.
- Uses the same Cognito `USER_PASSWORD_AUTH` flow as the app, over verified HTTPS.
- The password is used only during sign-in. Home Assistant stores the username, refresh token and optional Cognito device key in its configuration entries. Treat configuration backups as private.
- Supports SMS, TOTP and email/SMS OTP challenges. Finish account activation, mandatory password changes or initial MFA enrollment in the official app first.
- Refreshes and persists tokens, including token rotation. Expired sessions prompt reauthentication.
- Sends each command once and waits for its **reported** device value. A desired value alone is not confirmation. Unconfirmed commands produce an error without inventing a new device state.
- Blocks commands while offline, uninitialized or under technician control.
- Connectivity follows the app's thresholds: five minutes for newer CARDV3+/ESP32S3 controllers, up to 24 hours for legacy controllers. Check the last-update sensor when interpreting old readings.

The integration depends on the cloud API used by the Nirvana app. Server changes may require an integration update. Verify readings against the official app before setting up automations.

## Troubleshooting and feedback

If sign-in fails, check the error's **operation, Cognito code and HTTP status**. Version 0.1.1 fixes the incorrect authentication flow used in 0.1.0. Replace the component folder and restart Home Assistant when updating manually.

[Open an issue](https://github.com/vcadieux/home-assistant-nirvana/issues) with your Home Assistant version, integration version, heat-pump model and a description of the problem. Never include passwords, tokens, account emails, MAC addresses or raw cloud responses. Downloadable integration diagnostics contain field names and limited state indicators, not account identifiers or tokens.

## Development

Tested locally with Home Assistant **2024.12.5 / Python 3.12** and **2026.10.4 / Python 3.14**. See [VALIDATION.md](VALIDATION.md) for test scope and limitations.

```sh
# Python 3.14
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
python scripts/build_release.py
```

The published repository contains the independently written integration, tests and documentation. It excludes the original APK, extracted application code/assets and development environments.

## Support the project

If this integration is useful, you can [buy me a coffee through PayPal](https://www.paypal.com/donate/?business=vcadieux%40vincentcadieux.com&currency_code=CAD). Choose any amount in Canadian dollars. Recipient: **vcadieux@vincentcadieux.com**.

Donations are optional. All integration features remain free.

## License

[MIT](LICENSE) — Copyright © 2026 Vincent Cadieux.
