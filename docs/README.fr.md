[English](../README.md) · Français

# Nirvana Heat Pump pour Home Assistant

[☕ M’offrir un café avec PayPal](https://www.paypal.com/donate/?business=vcadieux%40vincentcadieux.com&currency_code=CAD)

Projet communautaire indépendant, sans affiliation ni approbation de Nirvana ou de Home Assistant.

Intégration personnalisée **cloud** pour les thermopompes Nirvana, construite à partir des contrats de l’app Android 4.0.7. Version 0.1.1 : fonctionnement confirmé par son premier utilisateur. Les tests automatisés couvrent le client et le chargement Home Assistant ; la compatibilité avec tous les modèles et firmwares n’est pas encore établie.

## Fonctions

Une entité `climate` par thermopompe permet d’afficher la température de l’eau, monter/descendre la consigne, choisir piscine ou spa et arrêter le chauffage. Le refroidissement est exposé uniquement si l’appareil annonce les capacités correspondantes.

L’intégration ajoute également :

- température de l’eau et température extérieure ;
- état : chauffage, refroidissement, repos, dégivrage, délai compresseur ou défaut ;
- profil de performance : silencieux ou éco selon le type, Smart et Boost si permis ;
- connexion de la thermopompe au cloud, défaut, signal Wi-Fi et dernière mise à jour.

Les champs absents d’un modèle apparaissent comme inconnus. Les pompes de filtration autonomes sont exclues de cette première version. L’intégration n’associe pas de nouveaux appareils au compte : faites d’abord l’association dans l’application Nirvana.

## Installation manuelle

1. Téléchargez et décompressez le ZIP depuis la [dernière version publiée](https://github.com/vcadieux/home-assistant-nirvana/releases/latest).
2. Copiez **le dossier `custom_components/nirvana_cloud`** dans le dossier de configuration de votre Home Assistant. Le résultat doit être :

   ```text
   /config/custom_components/nirvana_cloud/manifest.json
   /config/custom_components/nirvana_cloud/__init__.py
   /config/custom_components/nirvana_cloud/...
   ```

   `/config` est le chemin habituel dans Home Assistant OS. Pour Home Assistant Container/Core, utilisez le dossier qui contient votre `configuration.yaml`.

3. Redémarrez Home Assistant.
4. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**.
5. Cherchez **Nirvana Heat Pump (Cloud)**, puis saisissez les identifiants utilisés dans l’app Nirvana.
6. Si demandé, entrez le code reçu par SMS/courriel ou celui de l’application d’authentification.

Aucune entrée YAML de configuration n’est nécessaire. Home Assistant installe `pycognito==2024.5.1` au premier chargement ; il doit pouvoir accéder à Internet pour cette installation et pour les services Nirvana/Cognito.

## Installation avec HACS (dépôt personnalisé)

1. Dans HACS, ouvrez **Dépôts personnalisés**.
2. Ajoutez `https://github.com/vcadieux/home-assistant-nirvana` avec le type **Intégration**.
3. Recherchez **Nirvana Heat Pump (Cloud)** et téléchargez l’intégration.
4. Redémarrez Home Assistant, puis ajoutez l’intégration dans **Paramètres → Appareils et services**.

Le dépôt n’est pas inclus dans le catalogue par défaut de HACS. L’installation manuelle reste disponible si vous n’utilisez pas HACS.

## Dashboard

Ajoutez une carte **Thermostat**, puis sélectionnez l’entité `climate` créée par l’intégration. La consigne est celle de la piscine ou du spa actuellement sélectionné.

Dans le panneau détaillé du thermostat, choisissez le préréglage **Piscine / Spa**. Les modes chauffage/arrêt se règlent avec les commandes habituelles du thermostat. Les profils silencieux/éco/Smart/Boost sont dans l’entité **Performance**.

Un exemple de carte sans dépendance HACS se trouve dans [examples/dashboard.yaml](../examples/dashboard.yaml). Remplacez les identifiants d’entités de l’exemple par ceux de votre installation : les noms sont générés par Home Assistant selon la langue et le nom de l’appareil.

Exemple d’action pour une consigne de 28 °C si Home Assistant est configuré en Celsius :

```yaml
action: climate.set_temperature
target:
  entity_id: climate.piscine
data:
  temperature: 28
```

Exemple pour passer au spa :

```yaml
action: climate.set_preset_mode
target:
  entity_id: climate.piscine
data:
  preset_mode: spa
```

L’intégration laisse Home Assistant convertir les unités. Elle envoie ensuite les commandes dans l’unité native C/F de l’appareil, avec une consigne entière comme dans l’app originale. Une température hors plage est refusée. Une valeur fractionnaire est arrondie au degré natif le plus proche, comme dans l’app Nirvana ; cela permet aussi de régler depuis un Home Assistant en Celsius un appareil configuré en Fahrenheit. Les plafonds sont 35 °C / 95 °F pour la piscine et 40 °C / 104 °F pour le spa, avec les limites plus restrictives annoncées par la thermopompe.

## Fonctionnement

- Authentification Cognito **USER_PASSWORD_AUTH**, comme le parcours de connexion de l’app originale, puis accès à `https://nirvana.iot-endpoint.com` avec un jeton d’accès.
- Le mot de passe est utilisé uniquement pour la connexion. Home Assistant conserve l’identifiant, un jeton de renouvellement et éventuellement la clé d’un appareil Cognito confirmé dans ses entrées de configuration. Aucun identifiant de compte n’est intégré au ZIP.
- Les jetons renouvelés sont persistés, y compris en cas de rotation. Une session expirée déclenche une demande de reconnexion.
- Les codes MFA SMS, TOTP, SMS OTP et courriel OTP sont gérés. L’activation du compte, le changement obligatoire de mot de passe et la configuration initiale MFA doivent être terminés dans l’application officielle.
- Actualisation toutes les **30 secondes**, modifiable entre 15 et 300 secondes via **Configurer** sur l’intégration.
- Une commande est envoyée une seule fois et attend jusqu’à environ 20 secondes de confirmation dans les paramètres `reported`. Une modification de `desired` seule ne confirme pas la commande. En cas de délai dépassé, l’état reste celui effectivement remonté et une erreur indique que la commande n’est pas confirmée. Les temps de réseau peuvent prolonger cette attente.
- Les commandes d’un même appareil sont sérialisées. Elles sont refusées hors ligne, sans configuration valide ou sous contrôle d’un technicien. L’arrêt n’interrompt pas mécaniquement l’alimentation électrique.
- Le contrôle de disponibilité reprend les seuils de l’app : 5 minutes pour CARDV3+ / certains afficheurs ESP32S3, 24 heures pour les anciennes cartes. Le cloud peut donc conserver une dernière température longtemps sur un ancien modèle ; la date de mise à jour permet de le constater.

## Dépannage et validation sur votre appareil

Commencez par vérifier que les températures et le mode correspondent à l’app Nirvana. Essayez ensuite une petite modification de consigne et vérifiez son application sur l’afficheur ou dans l’app. Un premier utilisateur a confirmé le fonctionnement de la version 0.1.1 ; vérifiez les fonctions disponibles sur votre propre modèle.

Si la connexion échoue, vérifiez que le compte fonctionne dans l’app officielle et que son activation est terminée. En cas de session expirée, utilisez la demande de reconnexion de Home Assistant. Un appareil hors ligne reste visible mais ses mesures et commandes deviennent indisponibles ; le capteur de connexion affiche l’état déconnecté si le cloud répond.

Si le cloud répond avec une structure différente, l’intégration refuse de fabriquer des valeurs. Le diagnostic téléchargeable depuis Home Assistant contient les noms des champs reçus et des indicateurs d’état, sans jetons, courriel, nom d’appareil ou adresse MAC. Il peut aider à adapter le client à votre modèle.

Cette intégration dépend d’une API extraite de l’app, sans contrat de stabilité public vérifié. Une modification du service Nirvana peut nécessiter une mise à jour.

## Développement et preuves

Le code se trouve dans `custom_components/nirvana_cloud/`. Les tests n’utilisent aucun compte réel : réponses HTTP simulées, parcours Cognito identique à l’app, entités et services chargés dans Home Assistant. Voir [VALIDATION.md](../VALIDATION.md) pour les versions et résultats vérifiés. Pour reproduire les tests : `python -m pip install -r requirements-dev.txt` (Python 3.14).

```sh
python -m pytest -q
ruff check custom_components tests
ruff format --check custom_components tests
```

Le dépôt publie uniquement le code de l’intégration et sa documentation. Il ne contient ni APK, ni ressources graphiques ou code extrait de l’application originale, ni identifiants de compte.

Sources de référence : [entités Climate](https://contributors.home-assistant.io/core/entities/climate/), [lecture coordonnée des données](https://contributors.home-assistant.io/core/integrations/fetching-data/), [renouvellement des jetons Cognito](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GetTokensFromRefreshToken.html), [bibliothèque pycognito](https://github.com/pvizeli/pycognito).

## Mise à jour 0.1.1 — connexion

La version 0.1.0 sélectionnait le flux SRP à tort. L’inspection ciblée de la fonction `Zf` de l’app Android confirme qu’elle demande `USER_PASSWORD_AUTH`. La 0.1.1 reprend ce choix, ne bloque plus la connexion si la confirmation optionnelle d’un appareil Cognito échoue, et affiche l’étape et le code Cognito en cas de refus. Les journaux n’incluent ni mot de passe, ni jetons, ni réponses brutes du serveur.

Pour mettre à jour : remplacez le dossier `custom_components/nirvana_cloud` par celui du nouveau ZIP, redémarrez Home Assistant, puis recommencez l’ajout. Si un refus persiste, transmettez seulement le nom de l’étape, le code d’erreur et le statut HTTP affichés, jamais vos identifiants.

## Soutenir le projet

Si cette intégration vous est utile, vous pouvez [m’offrir un café via PayPal](https://www.paypal.com/donate/?business=vcadieux%40vincentcadieux.com&currency_code=CAD). Le montant est libre, en dollars canadiens. Destinataire : **vcadieux@vincentcadieux.com**. Le don est facultatif ; toutes les fonctions restent accessibles gratuitement.

## Licence

Code publié sous [licence MIT](../LICENSE).
