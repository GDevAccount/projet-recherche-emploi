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

Il n'y a ni tests ni linter configurés.

Deux variables d'environnement servent à l'hébergement (voir `Dockerfile`) : `DATA_DIR` déplace `jobs.db` et `cv.pdf` vers un volume, `APP_PASSWORD` active la demande de mot de passe dans `app.py`. Sans elles, le comportement local est inchangé.

L'instance en ligne tourne sur Fly.io (`fly.toml`) et se publie avec `fly deploy`. Les clés API et `APP_PASSWORD` y sont des secrets Fly, pas un `.env`.

## Architecture

Tout le code est dans `src/projet_recherche_emploi/`.

- `main.py` construit le graph : `searchJobs` → `FilterJobs` → `InsertJobs`. Les trois nœuds sont dans `node.py`, l'état partagé dans `state.py`.
- `job_repository.py` et `query_repository.py` sont les seuls accès à SQLite, respectivement pour les tables `jobs` et `search_queries`.
- `cv_reader.py` lit et enregistre le CV.
- `app.py` est l'interface Streamlit. Elle ne contient pas de logique métier : elle appelle les dépôts, `CV_reader` et le graph.
- `config.py` regroupe les constantes (chemins, modèle, recherches par défaut).

## Pièges

- **Importer `main.py` a des effets de bord.** Le module construit le graph et régénère `graph.png` via le service en ligne mermaid.ink. C'est pourquoi `__init__.py` et `app.py` l'importent localement, dans la fonction qui lance la recherche. Ne pas remonter cet import en tête de fichier.
- **Une vraie recherche coûte de l'argent.** Chaque exécution du graph consomme des crédits Tavily et OpenAI. Ne pas la lancer pour vérifier un changement sans l'accord de l'utilisateur ; tester les dépôts et l'interface sur une base temporaire.
- **Changer le schéma demande une migration.** Les tables sont créées par `CREATE TABLE IF NOT EXISTS` (ou équivalent) : modifier la requête de création n'a aucun effet sur un `jobs.db` existant. Il faut un `ALTER TABLE`, ou supprimer la base avec l'accord de l'utilisateur.
- **Les recherches par défaut ne sont insérées qu'une fois.** `DEFAULT_QUERIES` est écrit en base à la création de la table `search_queries`, pas quand elle est vide. C'est voulu : une recherche supprimée par l'utilisateur ne doit pas revenir.
- **SQLite enregistre les dates en UTC.** `created_at` et `applied_at` viennent de `CURRENT_TIMESTAMP`. La conversion en heure de Paris se fait à l'affichage, dans `to_local_time` de `app.py`.
- **Le tableau des offres n'a pas de `key`.** Le `st.data_editor` de `app.py` repart ainsi d'un état vierge dès que les données changent. Avec une clé, une coche en attente pourrait s'appliquer à la mauvaise ligne après un filtrage.
- **Sur Fly.io, seul `/data` survit à un redémarrage.** Le reste du disque est remis à zéro, et le volume monté sur `/data` (section `[mounts]` de `fly.toml`) n'est pas partagé entre machines. Tout fichier à conserver doit passer par `DATA_DIR`, et l'application doit rester sur une seule machine.
- **`save_cv` valide avant d'écrire.** Le CV en place n'est écrasé que si le nouveau PDF est lisible et contient du texte. Garder cet ordre.

## Conventions

- Commentaires, docstrings, messages de log et textes de l'interface sont en français ; les noms de variables et de fonctions sont en anglais.
- Les commentaires expliquent le pourquoi, pas le quoi, et restent rares.
- Chaque méthode publique d'un dépôt ouvre sa connexion, travaille dans un `with connection` (transaction), puis la ferme dans un `finally`. Les méthodes privées reçoivent la connexion en paramètre.
- Les dépôts renvoient des `list[dict]` en lecture, et un booléen ou un nombre de lignes en écriture.
- Les erreurs destinées à l'utilisateur sont des `ValueError` avec un message en français, affichable tel quel par `st.error`.
- Mettre à jour le README quand une commande, une table ou un réglage change.
