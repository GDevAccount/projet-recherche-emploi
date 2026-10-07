# Projet recherche emploi

Un agent qui cherche des offres d'emploi sur le web, ne garde que celles qui correspondent à votre CV, et les enregistre dans une base SQLite. Une interface [Streamlit](https://streamlit.io/) permet de déposer son CV, de choisir les postes recherchés, de lancer la recherche et de suivre ses candidatures.

À chaque recherche, seules les nouvelles pages sont évaluées : une offre déjà en base (même URL) n'est pas réinsérée, et une page déjà rejetée n'est pas soumise à nouveau au modèle.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (il installe lui-même Python 3.11 si besoin)
- Une clé API [Tavily](https://tavily.com/)
- Une clé API [OpenAI](https://platform.openai.com/)
- Votre CV au format PDF, avec du texte sélectionnable (un PDF scanné sera refusé)

## Installation

1. Installer les dépendances :

   ```bash
   uv sync
   ```

2. Copier `.env.example` vers `.env` à la racine du projet, puis y renseigner les valeurs :

   ```env
   TAVILY_API_KEY=tvly-...
   OPENAI_API_KEY=sk-...
   APP_PASSWORD=un-mot-de-passe-long
   ```

   `APP_PASSWORD` est facultatif en local : si la ligne est supprimée ou laissée vide, l'interface s'ouvre sans rien demander. Il est indispensable dès que l'application est accessible depuis internet (voir [Sécurité](#sécurité)).

## Lancer l'application

Depuis la racine du projet :

```bash
uv run streamlit run src/projet_recherche_emploi/app.py
```

L'interface s'ouvre dans le navigateur, à l'adresse `http://localhost:8501`.

La commande doit être lancée depuis la racine : `cv.pdf`, `jobs.db` et `graph.png` sont cherchés ou créés dans le dossier courant.

## Utiliser l'interface

1. **Déposer son CV.** Dans la barre latérale, choisir un PDF puis cliquer sur « Enregistrer ce CV ». Il est enregistré à la racine sous le nom `cv.pdf` et remplace le précédent. Les pages rejetées avec l'ancien CV sont alors oubliées : elles seront réévaluées à la prochaine recherche.
2. **Choisir les postes recherchés.** La barre latérale liste les recherches enregistrées. Chacune associe un type de contrat à une phrase de recherche, par exemple « offre d'emploi data engineer en CDI à Lyon ». Le formulaire en ajoute une, le bouton ✕ en supprime une. Elles sont conservées en base d'une session à l'autre.
3. **Lancer une recherche.** Le bouton « Lancer une recherche » est actif dès qu'un CV et au moins une recherche sont enregistrés. Une barre de progression suit les recherches Tavily puis les évaluations par OpenAI, ce qui peut prendre quelques minutes. La page indique ensuite le nombre de pages trouvées, de pages pas encore évaluées, d'offres retenues, de pages rejetées et de nouvelles offres en base.
4. **Suivre ses candidatures.** L'onglet « Offres retenues » liste les offres, de la plus récente à la plus ancienne, avec un lien vers l'annonce et la raison pour laquelle elle a été retenue. Cocher « Postulé » enregistre la candidature et sa date. Au-dessus du tableau, un filtre par type de contrat, un champ de recherche (sur le titre de l'offre et la raison donnée par le modèle, par exemple pour retrouver une entreprise) et un interrupteur masquant les offres déjà postulées sont disponibles.
5. **Supprimer une offre.** Cocher « Supprimer » sur une ou plusieurs lignes, puis cliquer sur le bouton « Supprimer N offre(s) » qui apparaît sous le tableau. Une offre supprimée ne revient pas aux recherches suivantes.

6. **Comprendre les rejets.** L'onglet « Pages rejetées » liste les pages écartées par le modèle, avec la raison donnée. Chaque page est classée « Pas une offre valable » (liste d'offres, article, offre expirée ou hors région parisienne) ou « Hors profil » (vraie offre, mais qui ne correspond pas au CV). Des filtres par motif et par recherche d'origine, et un champ de recherche, aident à repérer ce qui fait perdre des offres.

Chaque recherche consomme des crédits Tavily (une recherche avancée par poste recherché) et OpenAI (un appel par résultat qui n'a pas déjà été évalué, jusqu'à 20 par poste recherché).

Au premier lancement d'une recherche, un schéma du graph est généré dans `graph.png`. Il est produit par le service en ligne mermaid.ink, donc une connexion internet est nécessaire.

### Sans l'interface

La recherche seule peut aussi être lancée en ligne de commande, avec le CV et les recherches déjà enregistrés :

```bash
uv run projet-recherche-emploi
```

## Héberger l'application pour quelqu'un d'autre

Pour qu'une personne l'utilise sans rien installer, l'application peut tourner sur un serveur : elle l'ouvre dans son navigateur, et les clés API restent sur le serveur. Une instance sert une seule personne (un CV, une base).

Le `Dockerfile` fourni construit l'image. L'hébergeur doit proposer un volume persistant, sinon le CV et la base sont perdus à chaque redémarrage.

| À régler chez l'hébergeur | Valeur |
|---|---|
| Variable `TAVILY_API_KEY` | Clé Tavily |
| Variable `OPENAI_API_KEY` | Clé OpenAI |
| Variable `APP_PASSWORD` | Mot de passe demandé à l'ouverture de la page |
| Volume persistant | Monté sur `/data` |
| Port exposé | `8501` |

Sans `APP_PASSWORD`, la page est ouverte à quiconque connaît l'adresse, et chaque recherche est facturée sur vos clés. Les précautions à prendre sont détaillées dans [Sécurité](#sécurité).

Pour essayer l'image en local :

```bash
docker build -t recherche-emploi .
docker run -p 8501:8501 -v recherche-emploi-data:/data --env-file .env -e APP_PASSWORD=un-mot-de-passe recherche-emploi
```

### Instance déployée sur Fly.io

Le projet est déployé sur [Fly.io](https://fly.io/), à l'adresse <https://projet-recherche-emploi.fly.dev/>. La configuration est dans `fly.toml`.

Cette instance demande un mot de passe à l'ouverture. Il n'est pas dans ce dépôt : pour la tester, le demander à l'auteur.

À faire une seule fois, avant le premier déploiement :

```bash
fly scale count 1                                # une seule machine : un volume n'est pas partagé entre machines
fly volumes create data --region cdg --size 1    # volume monté sur /data (CV et base)
fly secrets set TAVILY_API_KEY=... OPENAI_API_KEY=... APP_PASSWORD=...
```

Une nouvelle version est publiée automatiquement à chaque push sur la branche `main`, par le workflow GitHub Actions `.github/workflows/fly-deploy.yml`. Le déroulement se suit dans l'onglet **Actions** du dépôt. L'instance redémarre à chaque déploiement : le volume `/data` est conservé, mais une recherche en cours est interrompue.

Ce workflow a besoin d'un jeton Fly.io, enregistré une seule fois comme secret `FLY_API_TOKEN` du dépôt GitHub :

```bash
fly tokens create deploy -x 999999h    # jeton limité à cette application
gh secret set FLY_API_TOKEN            # coller le jeton, préfixe « FlyV1 » compris
```

Pour publier à la main, sans passer par GitHub :

```bash
fly deploy
```

Pour changer le mot de passe (la machine redémarre avec la nouvelle valeur) :

```bash
fly secrets set APP_PASSWORD=nouveau-mot-de-passe
```

## Sécurité

L'application n'a pas de comptes utilisateurs : la seule protection est le mot de passe unique `APP_PASSWORD`. Quiconque le connaît peut lire et remplacer le CV, modifier les recherches et lancer des recherches facturées sur vos clés.

- **Toujours définir `APP_PASSWORD` sur une instance en ligne.** Le mot de passe est demandé à chaque nouvelle session du navigateur.
- **Choisir un mot de passe long et aléatoire.** Le nombre d'essais n'est pas limité : un mot de passe court peut être trouvé par essais successifs.
- **Ne jamais écrire de secret dans le dépôt.** Les clés et le mot de passe vont dans `.env` en local (ignoré par Git et exclu de l'image Docker) et dans les secrets de l'hébergeur en ligne. Le jeton de déploiement Fly.io va dans les secrets du dépôt GitHub. `.env.example` ne contient que des valeurs fictives.
- **Utiliser des clés API dédiées à l'instance, avec un plafond de dépense** chez Tavily et OpenAI. Si le mot de passe fuit, la facture reste bornée et les clés se révoquent sans toucher aux autres projets.
- **Garder le HTTPS.** Sur Fly.io, `force_https = true` dans `fly.toml` évite que le mot de passe circule en clair. Chez un autre hébergeur, vérifier que la page n'est servie qu'en HTTPS.
- **En cas de doute, tout renouveler.** Changer `APP_PASSWORD`, puis révoquer et recréer les deux clés API.

## Fonctionnement

La recherche est un graph [LangGraph](https://langchain-ai.github.io/langgraph/) de quatre étapes exécutées à la suite :

| Étape | Rôle |
|---|---|
| `searchJobs` | Lance une recherche Tavily par poste recherché enregistré, limitée aux sites d'emploi et aux annonces de la dernière semaine, puis supprime les doublons. |
| `FilterDuplicates` | Écarte les pages dont l'URL est déjà en base, offres supprimées et pages rejetées comprises, pour ne pas les faire évaluer à nouveau. |
| `FilterJobs` | Lit le CV (PDF) et demande à un modèle OpenAI, pour chaque page restante, si la page est une vraie offre (et non une liste d'offres) et si elle correspond au profil. |
| `InsertJobs` | Enregistre les offres retenues et les pages rejetées dans la base SQLite `jobs.db`. |

## Base de données

`jobs.db` contient trois tables, créées automatiquement. Une base créée par une version antérieure est mise à niveau au premier lancement, sans perte de lignes.

Table `jobs`, les offres retenues :

| Colonne | Contenu |
|---|---|
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `url` | Lien de l'offre (unique par utilisateur) |
| `title` | Titre de la page |
| `content` | Extrait de l'annonce |
| `score` | Pertinence estimée par Tavily, entre 0 et 1 |
| `contract_type` | Type de contrat de la recherche qui a trouvé l'offre |
| `query` | Recherche qui a trouvé l'offre |
| `match_reason` | Justification du modèle pour avoir retenu l'offre |
| `applied` | `1` si vous avez postulé, `0` sinon |
| `applied_at` | Date de candidature (UTC), vide tant que vous n'avez pas postulé |
| `created_at` | Date d'insertion (UTC) |
| `deleted` | `1` si vous avez supprimé l'offre : elle n'est plus affichée, mais sa ligne reste pour qu'elle ne soit pas réinsérée |

Table `rejected_jobs`, les pages rejetées par le modèle. Elle sert à ne pas payer une nouvelle évaluation pour une page déjà rejetée. Elle est vidée quand un nouveau CV est enregistré.

| Colonne | Contenu |
|---|---|
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `url` | Lien de la page (unique par utilisateur) |
| `title` | Titre de la page |
| `contract_type` | Type de contrat de la recherche qui a trouvé la page |
| `query` | Recherche qui a trouvé la page |
| `is_real_offer` | `1` si le modèle y a vu une vraie offre, `0` sinon |
| `matches_cv` | `1` si le modèle a jugé que le poste correspond au CV, `0` sinon |
| `reject_reason` | Justification du modèle pour avoir rejeté la page |
| `created_at` | Date du rejet (UTC) |

Table `search_queries`, les postes recherchés :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la recherche |
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `contract_type` | Type de contrat (`CDI`, `freelance`, `CDD`, `alternance` ou `stage`) |
| `query` | Phrase envoyée à Tavily (unique par utilisateur) |
| `created_at` | Date d'ajout (UTC) |

## Configuration

Les postes recherchés et le CV se règlent dans l'interface. Le reste se règle dans le code :

| Réglage | Fichier | Valeur par défaut |
|---|---|---|
| Dossier de la base et du CV (`DATA_DIR`) | variable d'environnement | dossier courant |
| Nom de la base (`DB_PATH`) | `src/projet_recherche_emploi/config.py` | `jobs.db` |
| Nom du CV (`CV_PATH`) | `src/projet_recherche_emploi/config.py` | `cv.pdf` |
| Mot de passe de l'interface (`APP_PASSWORD`) | variable d'environnement | aucun |
| Modèle OpenAI du filtre (`FILTER_MODEL`) | `src/projet_recherche_emploi/config.py` | `gpt-5-mini` |
| Taille maximale de page envoyée au modèle (`MAX_PAGE_CHARS`) | `src/projet_recherche_emploi/config.py` | `8000` |
| Recherches créées avec la base (`DEFAULT_QUERIES`) | `src/projet_recherche_emploi/config.py` | 2 recherches CDI, 2 freelance (ingénieur IA) |
| Types de contrat proposés (`CONTRACT_TYPES`) | `src/projet_recherche_emploi/app.py` | CDI, freelance, CDD, alternance, stage |
| Sites interrogés (`JOB_SITES`) | `src/projet_recherche_emploi/node.py` | 15 sites d'emploi |
| Critères du filtre (`FILTER_PROMPT`) | `src/projet_recherche_emploi/node.py` | — |

Après une modification de `FILTER_PROMPT`, les pages déjà rejetées ne sont pas réévaluées. Pour les soumettre à nouveau, vider la table : `sqlite3 jobs.db "DELETE FROM rejected_jobs"`.

`DEFAULT_QUERIES` n'est utilisé qu'à la création de la base : une fois les recherches modifiées dans l'interface, il n'a plus d'effet.

## Tests

```bash
uv run pytest
```

Les tests vérifient la mise à niveau d'une base existante. Ils tournent sur une base temporaire et n'appellent ni Tavily ni OpenAI.

## Structure du projet

```
src/projet_recherche_emploi/
├── app.py               # interface Streamlit
├── __init__.py          # point d'entrée de la commande projet-recherche-emploi
├── main.py              # construction du graph LangGraph
├── node.py              # les quatre étapes : search_jobs, filter_duplicates, filter_jobs, insert_jobs
├── state.py             # état partagé entre les étapes
├── config.py            # réglages (chemins, modèle, recherches par défaut)
├── migration.py         # mise à niveau des bases créées avant la colonne user_id
├── cv_reader.py         # lecture et enregistrement du CV en PDF
├── job_repository.py           # table des offres : insertion, lecture, suivi des candidatures, suppression
├── rejected_job_repository.py  # table des pages rejetées : insertion, lecture, vidage
└── query_repository.py         # table des postes recherchés : lecture, ajout, suppression
```
