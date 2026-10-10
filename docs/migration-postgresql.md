# Passer de SQLite à PostgreSQL : inventaire

Ce document liste ce qui, dans le code, suppose une base SQLite ou un seul processus. Il sert à deux choses : savoir ce que coûterait la bascule, et vérifier que ce coût ne monte pas au fil des développements.

Relevé fait le 2026-10-09, sur le schéma à la migration 0014. Les estimations sont des ordres de grandeur, pour une personne qui connaît le code.

## Décision

L'application reste sur SQLite et sur une seule machine. La bascule vers PostgreSQL se fait **avant l'ouverture des paiements** : c'est le moment où une coupure ou une erreur de migration commence à coûter cher.

Elle est avancée si l'un de ces signaux apparaît :

- des erreurs `OperationalError` (« database is locked ») dans la carte Santé de la rubrique Suivi ;
- des recherches simultanées qui se ralentissent entre elles ;
- le besoin de déployer sans interrompre les recherches en cours.

Avant d'ajouter des machines, grossir celle qui existe (`[[vm]]` de `fly.toml`) : une recherche passe l'essentiel de son temps à attendre Tavily et OpenAI.

## Pourquoi plusieurs machines ne fonctionnent pas aujourd'hui

- Un volume Fly.io n'est attaché qu'à une machine : deux machines auraient chacune leur `jobs.db`.
- SQLite ne se partage pas sur un disque réseau : ses verrous n'y sont pas fiables.
- Une partie de l'état vit en mémoire d'un processus (voir plus bas).

Les variantes de SQLite répliqué n'acceptent les écritures que sur une machine : elles ne règlent pas le problème.

## Ce qui est lié à SQLite

| Où | Ce qui est propre à SQLite | Travail | Estimation |
|---|---|---|---|
| `data/database.py`, `Database.__init__` | Moteur construit sur un chemin de fichier, sans pool de connexions | Lire une adresse de base dans `Settings`, garder un pool | 0,5 jour |
| `data/database.py`, `_use_explicit_transactions` | Contourne le pilote `sqlite3`, qui n'ouvre pas de transaction pour un `CREATE` | À retirer : PostgreSQL rend ses migrations transactionnelles | compris ci-dessus |
| `data/database.py`, `_backup` | Copie du fichier avant chaque migration, avec le pilote `sqlite3` | Remplacer par une sauvegarde de la base hébergée, prise avant le déploiement | 0,5 jour |
| `data/database.py`, `purge_user_from_backups` et `_purge_user` | Ouvre chaque copie, lit `sqlite_master` et `PRAGMA table_info`, termine par `VACUUM` | Disparaît avec les copies. Reste à dire, dans les règles de confidentialité, combien de temps les sauvegardes de l'hébergeur gardent un compte supprimé | 0,5 jour |
| `data/models.py`, `UtcDateTime` | Dates en texte, au format de `CURRENT_TIMESTAMP` de SQLite, comparées comme du texte | Passer à `TIMESTAMP WITH TIME ZONE` ; convertir les données | 1 jour |
| `data/models.py`, `IntBool` | Booléens en 0 ou 1 | Passer à `BOOLEAN` ; convertir les données | compris ci-dessus |
| `data/models.py`, 12 colonnes | `server_default=text("CURRENT_TIMESTAMP")` rend du texte sous SQLite | Fonctionne sous PostgreSQL une fois la colonne typée | compris ci-dessus |
| 5 dépôts : `job`, `rejected_job`, `query`, `user`, `cv_text` | `from sqlalchemy.dialects.sqlite import insert`, pour `on_conflict_do_nothing` et `on_conflict_do_update` | Même API dans `sqlalchemy.dialects.postgresql` : changer l'import, relire les contraintes visées | 0,5 jour |
| `usage_repository.py`, `archive_account` | `func.strftime` pour tirer le mois d'une date | `to_char` sous PostgreSQL | compris ci-dessus |
| `search_run_repository.py`, `record_run` | `result.lastrowid` | `RETURNING`, comme le fait déjà l'autre branche de la méthode | compris ci-dessus |
| `search_run_repository.py`, `record_run` | Le quota tient en une requête « compter puis insérer ». C'est sûr sous SQLite, qui n'écrit qu'une transaction à la fois, pas sous PostgreSQL | Verrou par utilisateur (`pg_advisory_xact_lock`) ou niveau d'isolation « serializable » | 0,5 jour |
| `data/migrations/versions/`, 14 fichiers | Cinq contiennent du SQL brut pour SQLite ; `env.py` active `render_as_batch` | Ne pas les rejouer : un schéma initial neuf pour PostgreSQL, et les anciennes migrations archivées | 0,5 jour |
| `account_service.py`, `delete_account` | Garde la ligne du compte parce que SQLite redonnerait son identifiant | Sans objet sous PostgreSQL, mais sans danger : laisser tel quel | 0 |
| `tests/` | Base temporaire dans un fichier ; `test_schema.py`, `test_auth.py`, `test_services.py` et `conftest.py` ouvrent `sqlite3` ou un chemin de base | Lancer PostgreSQL pour les tests, en local et dans le workflow GitHub ; reprendre ces tests | 1 à 2 jours |
| `Dockerfile`, `fly.toml`, `Settings` | `DATA_DIR`, volume monté sur `/data`, migration au démarrage du conteneur | Adresse de la base en secret Fly ; migration lancée une seule fois par déploiement (`release_command`) ; le volume ne sert plus | 0,5 jour |
| `assistant_passages.embedding` | Vecteurs en JSON dans une colonne de texte, comparés en Python | Fonctionne tel quel. `pgvector` ne vaut la peine que si les textes dépassent quelques milliers de passages | 0 |
| Données existantes | Un fichier `jobs.db` | Script de copie table par table, avec conversion des dates et des booléens ; répétition sur une copie avant la bascule | 1 jour |

## Ce qui suppose un seul processus

Tout ceci doit passer en base avant de lancer une seconde machine. Avec PostgreSQL mais une seule machine, rien de cela n'empêche de fonctionner.

| Où | Ce qui est en mémoire | Travail | Estimation |
|---|---|---|---|
| `SearchService._running` | Utilisateurs dont une recherche tourne. Sert à refuser une seconde recherche, à refuser la suppression d'un compte, à `search_running` de `/api/me` et à reconnaître une recherche interrompue | L'état `running` de `search_runs` existe déjà : y ajouter un battement (`heartbeat_at`), et décider sur lui | 1 jour |
| `SearchService._describe_runs`, `HealthService.get_overview`, `alert_on_interrupted_runs` | « Resté en cours alors que rien ne tourne ici » veut dire interrompu | Avec plusieurs machines : interrompu si le battement est trop ancien | compris ci-dessus |
| `AlertService._last_sent` | Dernier envoi de chaque alerte | Une table `alerts_sent`, ou accepter un doublon par machine | 0,5 jour |
| `AccountService._last_purge_day` | La purge des comptes inactifs ne tourne qu'une fois par jour | Sans danger à plusieurs : la purge ne trouve plus rien la seconde fois. À laisser | 0 |
| `api/routers/searches.py` | La recherche tourne dans un fil du processus qui a reçu la requête | Fonctionne à plusieurs machines. Un déploiement l'interrompt toujours : la sortir dans une file de tâches est un autre chantier | hors périmètre |
| `AssistantService._index` | Passages et vecteurs relus de la base à la première question | Fonctionne à plusieurs machines : chacune relit la même table. Deux machines qui démarrent ensemble sur un texte modifié peuvent écrire ses passages en double, sans effet sur les réponses | 0 |
| `container.py`, `get_container` | Un conteneur par processus | Fonctionne tel quel | 0 |

## Total

Entre 6 et 9 jours pour basculer sur PostgreSQL avec une seule machine, dont 2 pour préparer plusieurs machines. Le plus gros poste est celui des tests.

## Ordre proposé le jour venu

1. Types de colonnes, imports de dialecte et requêtes : le code fonctionne sur les deux bases, les tests passent sur les deux.
2. Schéma initial PostgreSQL et script de copie des données, répétés sur une copie de la base en ligne.
3. Sauvegardes de l'hébergeur à la place des copies d'avant migration ; règles de confidentialité mises à jour.
4. Bascule : arrêt de l'instance, copie, vérification des comptes de lignes, redémarrage sur PostgreSQL. Le fichier `jobs.db` est gardé une semaine.
5. État en mémoire passé en base, puis seconde machine.

## Pour que ce coût ne monte pas

Les règles sont dans `CLAUDE.md`, au point « La base doit pouvoir changer ». En résumé :

- pas de SQL propre à SQLite dans du code nouveau ;
- pas de nouvel état partagé gardé en mémoire d'un processus ;
- pas d'accès au fichier de la base hors de `data/database.py`.

Mettre ce document à jour quand une ligne des tableaux ci-dessus change ou s'ajoute.
