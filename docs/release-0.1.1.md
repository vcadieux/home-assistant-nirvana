# Nirvana Cloud 0.1.1

First public release of the Nirvana heat-pump integration for Home Assistant.

- Water temperature, target adjustment and pool/spa selection.
- Heating/off controls and conditional cooling support.
- Model-dependent performance profiles and diagnostic sensors.
- UI sign-in, MFA, token refresh and French/English translations.
- Corrected authentication flow matching the Nirvana app.

The first user has confirmed it working. Automated tests: 41 passing on Home Assistant 2024.12.5 and 2026.10.4. Compatibility with all Nirvana models is not yet established.

Install through a custom HACS repository, or download and extract `nirvana-cloud-0.1.1.zip`, copy `custom_components/nirvana_cloud` to your Home Assistant configuration directory, restart, then add the integration.

[Installation instructions](https://github.com/vcadieux/home-assistant-nirvana#install-with-hacs) · [Instructions en français](https://github.com/vcadieux/home-assistant-nirvana/blob/main/docs/README.fr.md)

[☕ Support development through PayPal](https://www.paypal.com/donate/?business=vcadieux%40vincentcadieux.com&currency_code=CAD)
