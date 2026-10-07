# CLAUDE.md

Agent de recherche d'emploi : un graph LangGraph cherche des offres avec Tavily, les filtre avec un modèle OpenAI selon le CV, et les stocke en SQLite. Une interface Streamlit pilote le tout. Le README décrit l'usage ; ce fichier ne couvre que ce qu'il faut savoir pour modifier le code.

## Commandes

Toutes se lancent depuis la racine du projet, car `jobs.db`, `cv.pdf` et `graph.png` sont des chemins relatifs au dossier courant.

```bash
uv sync                                                   # installer les dépendances
uv run streamlit run src/projet_recherche_emploi/app.py   # interface
uv run projet-recherche-emploi                            # recherche seule, sans interface
uv add <paquet>                                           # ajouter une dépendance
```

```bash
uv run pytest                                             # tests des dépôts, sur une base temporaire
```

Les tests (`tests/`) couvrent la migration de la base et le cloisonnement des dépôts entre utilisateurs, pas l'interface ni le graph. Il n'y a pas de linter configuré.

Les clés `TAVILY_API_KEY` et `OPENAI_API_KEY` sont lues dans `.env` (modèle : `.env.example`), chargé par `load_dotenv()` dans `node.py` et `app.py`. Ne jamais afficher ni committer le contenu de `.env`.

Deux autres variables sont facultatives : `DATA_DIR` déplace `jobs.db` et `cv.pdf` vers un volume (voir `Dockerfile`), `APP_PASSWORD` active la demande de mot de passe dans `app.py`. Comme `.env.example` contient `APP_PASSWORD`, l'interface locale demande aussi le mot de passe, sauf si la ligne est vide ou absente.

L'instance en ligne tourne sur Fly.io (`fly.toml`). Elle est publiée automatiquement à chaque push sur `main` par `.github/workflows/fly-deploy.yml` ; `fly deploy` reste possible à la main. Les clés API et `APP_PASSWORD` y sont des secrets Fly, pas un `.env`. Le jeton utilisé par le workflow est le secret GitHub `FLY_API_TOKEN`.

## Architecture

Tout le code est dans `src/projet_recherche_emploi/`.

- `main.py` construit le graph : `searchJobs` → `FilterDuplicates` → `FilterJobs` → `InsertJobs`. Les quatre nœuds sont dans `node.py`, l'état partagé dans `state.py`.
- `job_repository.py`, `rejected_job_repository.py` et `query_repository.py` sont les seuls accès à SQLite, respectivement pour les tables `jobs`, `rejected_jobs` et `search_queries`.
- `cv_reader.py` lit et enregistre le CV.
- `app.py` est l'interface Streamlit. Elle ne contient pas de logique métier : elle appelle les dépôts, `CV_reader` et le graph.
- `config.py` regroupe les constantes (chemins, modèle, recherches par défaut).

## Pièges

- **Importer `main.py` a des effets de bord.** Le module construit le graph et régénère `graph.png` via le service en ligne mermaid.ink. C'est pourquoi `__init__.py` et `app.py` l'importent localement, dans la fonction qui lance la recherche. Ne pas remonter cet import en tête de fichier.
- **Une vraie recherche coûte de l'argent.** Chaque exécution du graph consomme des crédits Tavily et OpenAI. Ne pas la lancer pour vérifier un changement sans l'accord de l'utilisateur ; tester les dépôts et l'interface sur une base temporaire.
- **Changer le schéma demande une migration.** Les tables sont créées par `CREATE TABLE IF NOT EXISTS` (ou équivalent) : modifier la requête de création n'a aucun effet sur un `jobs.db` existant. Il faut un `ALTER TABLE`, ou supprimer la base avec l'accord de l'utilisateur. Modèle à suivre : la colonne `deleted`, ajoutée dans `JobRepository._create_table` après un `PRAGMA table_info`. Changer une clé primaire ou une contrainte d'unicité demande de recréer la table : voir `add_user_id` dans `migration.py`, qui ouvre lui-même sa transaction parce que Python n'en ouvre pas pour un `ALTER` ou un `CREATE`. La base en ligne (volume Fly.io) ne se migre que par ce biais.
- **Toute requête SQL doit filtrer sur `user_id`.** Chaque dépôt reçoit l'utilisateur à sa création (`JobRepository(DB_PATH, user_id)`) et ne lit ni ne modifie que ses lignes. Une requête écrite sans `user_id` montrerait les données d'un utilisateur à un autre : `tests/test_user_isolation.py` couvre chaque méthode publique, ajouter un cas pour toute nouvelle méthode. Pour l'instant `app.py` et `node.py` ne passent pas d'utilisateur, donc tout tourne avec `DEFAULT_USER_ID` (1) : l'application reste mono-utilisateur.
- **Les recherches par défaut ne vont qu'à l'utilisateur 1.** `DEFAULT_QUERIES` est calé sur le profil de l'auteur : un autre utilisateur part d'une liste vide.
- **Supprimer une offre ne supprime pas sa ligne.** `delete_jobs` passe `deleted` à 1 et `list_jobs` masque ces lignes. C'est voulu : l'URL reste en base, donc `INSERT OR IGNORE` empêche l'offre de revenir à la recherche suivante. Toute lecture de `jobs` destinée à l'affichage doit filtrer sur `deleted = 0` ; `list_known_urls` ne filtre pas, exprès, pour que le nœud `FilterDuplicates` écarte aussi les offres supprimées avant l'appel au modèle.
- **Un rejet du modèle est mémorisé.** `InsertJobs` écrit les pages rejetées dans `rejected_jobs`, et `FilterDuplicates` écarte leurs URL pour ne pas payer une seconde évaluation. La table n'est vidée que par `render_cv` de `app.py`, à l'enregistrement d'un nouveau CV. Après un changement de `FILTER_PROMPT`, les anciens rejets restent : il faut vider la table à la main pour les faire réévaluer.
- **La région parisienne est écrite en dur dans `FILTER_PROMPT`.** Le filtre de `node.py` rejette toute offre hors Île-de-France, quelle que soit la recherche enregistrée. Une recherche « à Lyon » ajoutée dans l'interface ne donnera donc rien tant que le prompt n'est pas modifié.
- **`cv.pdf` à la racine est versionné.** C'est le CV de l'auteur. Déposer un autre CV dans l'interface en local l'écrase : ne pas committer ce changement par mégarde. Il est exclu de l'image par `.dockerignore` ; en ligne, le CV vient du volume.
- **Les recherches par défaut ne sont insérées qu'une fois.** `DEFAULT_QUERIES` est écrit en base à la création de la table `search_queries`, pas quand elle est vide. C'est voulu : une recherche supprimée par l'utilisateur ne doit pas revenir.
- **SQLite enregistre les dates en UTC.** `created_at` et `applied_at` viennent de `CURRENT_TIMESTAMP`. La conversion en heure de Paris se fait à l'affichage, dans `to_local_time` de `app.py`.
- **Le tableau des offres n'a pas de `key`.** Le `st.data_editor` de `app.py` repart ainsi d'un état vierge dès que les données changent. Avec une clé, une coche en attente pourrait s'appliquer à la mauvaise ligne après un filtrage.
- **Pousser sur `main` met en ligne.** Le workflow ne lance pas les tests et n'a aucune étape de validation : tout commit poussé sur `main` est déployé et redémarre l'instance, ce qui interrompt une recherche en cours. Ne pas pousser sans l'accord de l'utilisateur.
- **Sur Fly.io, seul `/data` survit à un redémarrage.** Le reste du disque est remis à zéro, et le volume monté sur `/data` (section `[mounts]` de `fly.toml`) n'est pas partagé entre machines. Tout fichier à conserver doit passer par `DATA_DIR`, et l'application doit rester sur une seule machine.
- **Rien ne s'affiche avant `check_password()`.** Dans `main()` de `app.py`, tout rendu et tout accès aux dépôts viennent après ce contrôle. Un nouvel élément d'interface placé avant serait visible sans mot de passe sur l'instance en ligne.
- **`save_cv` valide avant d'écrire.** Le CV en place n'est écrasé que si le nouveau PDF est lisible et contient du texte. Garder cet ordre.

## Conventions

- Commentaires, docstrings, messages de log et textes de l'interface sont en français ; les noms de variables et de fonctions sont en anglais.
- Les commentaires expliquent le pourquoi, pas le quoi, et restent rares.
- Chaque méthode publique d'un dépôt ouvre sa connexion, travaille dans un `with connection` (transaction), puis la ferme dans un `finally`. Les méthodes privées reçoivent la connexion en paramètre.
- Les dépôts renvoient des `list[dict]` en lecture, et un booléen ou un nombre de lignes en écriture.
- Les erreurs destinées à l'utilisateur sont des `ValueError` avec un message en français, affichable tel quel par `st.error`.
- Mettre à jour le README quand une commande, une table ou un réglage change.
