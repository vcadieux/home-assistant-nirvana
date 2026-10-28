# Validation — Nirvana Cloud 0.1.1

Date : 28 octobre 2026.

| Environnement | Résultat |
|---|---|
| Python 3.12.14 / Home Assistant 2024.12.5 | 41 tests réussis |
| Python 3.14.10 / Home Assistant 2026.10.4 | 41 tests réussis |
| Ruff : analyse statique et formatage | Réussis |

Les tests utilisent les vrais modules et plateformes Home Assistant, le parcours `USER_PASSWORD_AUTH` de l’app et des réponses HTTP simulées. Aucun identifiant réel, aucun appel au cloud Nirvana et aucune commande matérielle n’ont été utilisés.

Couverture fonctionnelle vérifiée :

- flux `USER_PASSWORD_AUTH`, identifiant canonique et code MFA ;
- confirmation d’appareil optionnelle : son rejet ne fait pas échouer une connexion valide ;
- diagnostic du refus Cognito par étape, code autorisé et statut HTTP, sans réponse brute ni secrets ;
- confirmation d’un nouvel appareil Cognito et utilisation de sa clé au renouvellement ;
- renouvellement concurrent, rotation persistable et nouvelle tentative après HTTP 401 ;
- erreurs cloud nettoyées, limites de débit et formats inattendus ;
- valeurs désirées / remontées, champs nuls, températures C/F et conversion des consignes ;
- limites piscine/spa, état hors ligne, contrôle technicien et configuration non initialisée ;
- confirmation des commandes sur `reported`, délai dépassé sans renvoi automatique ni affichage optimiste ;
- chargement réel des plateformes `climate`, `sensor`, `binary_sensor`, `select`, appel du service `climate.set_temperature` et déchargement ;
- création d’une entrée sans conservation du mot de passe ;
- rotation des jetons sans rechargement de l’intégration, changement de fréquence avec rechargement.

Les quelques avertissements des tests proviennent de dépendances de l’environnement de test ; aucun échec n’est masqué.

L’adaptateur de tests aioresponses tient compte du nouvel argument `stream_writer` d’aiohttp. Les tests initialisent explicitement les registres et auxiliaires Home Assistant, sans démarrer les serveurs HTTP ni la découverte réseau.

## Validation restant à faire sur le matériel

1. Vérifier l’authentification réelle et les éventuelles politiques Cognito propres au compte.
2. Comparer températures, unités, modes et disponibilité avec l’application Nirvana.
3. Vérifier le schéma `desired` / `reported` réel : les noms de champs et contrats proviennent du code livré, pas d’une capture de réponses serveur.
4. Vérifier la confirmation d’une petite modification de consigne, puis piscine/spa/arrêt, selon les capacités du modèle.
5. Vérifier les profils de performance et le refroidissement si le modèle les annonce.

Il ne faut pas considérer le passage des tests simulés comme une certification de fonctionnement avec tous les firmwares Nirvana.

## Reproduire

Créer un environnement Python 3.14, puis :

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check custom_components tests
ruff format --check custom_components tests
```

Pour la vérification de compatibilité plus ancienne, utiliser Python 3.12 et remplacer le pin Home Assistant par `2024.12.5`.

## Correctif de la version 0.1.1

La fonction `Zf` de l’app Android sélectionne explicitement `USER_PASSWORD_AUTH`. La première version de l’intégration avait sélectionné SRP en se basant sur la bibliothèque embarquée, ce qui ne reflétait pas ce point d’entrée. Le test de contrat de connexion vérifie désormais le flux et le corps de la requête, y compris la conservation exacte des espaces du mot de passe. La 0.1.1 corrige cette divergence. Son premier utilisateur a ensuite confirmé le fonctionnement sur son installation ; ce retour ne certifie pas tous les modèles et firmwares.

Les preuves d’analyse locales sont conservées hors du dépôt public ; aucun code extrait de l’app n’est redistribué.
