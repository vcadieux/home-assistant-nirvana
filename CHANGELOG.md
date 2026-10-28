# Changelog

## 0.1.1

First public release, reported working by its first user.

- Climate entity with water temperature, pool/spa targets and heating/off controls.
- Conditional cooling support and a model-dependent performance selector.
- Temperature, status, connectivity and diagnostic sensors.
- UI sign-in, MFA, token refresh and reauthentication.
- Corrected sign-in to use `USER_PASSWORD_AUTH`, matching the Nirvana app.
- Optional device confirmation no longer rejects an otherwise valid sign-in.
- Safe Cognito diagnostics show the operation, exception code and HTTP status.
- French and English UI translations, installation guides and dashboard example.

## 0.1.0

Private prototype. Its SRP sign-in flow was incompatible with the app's selected authentication flow. Upgrade to 0.1.1.
