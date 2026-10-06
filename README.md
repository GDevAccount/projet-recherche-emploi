# Projet recherche emploi

Un agent qui cherche des offres d'emploi sur le web, ne garde que celles qui correspondent à votre CV, et les enregistre dans une base SQLite. Une interface [Streamlit](https://streamlit.io/) permet de déposer son CV, de choisir les postes recherchés, de lancer la recherche et de suivre ses candidatures.

À chaque recherche, seules les nouvelles offres sont ajoutées : une offre déjà en base (même URL) n'est pas réinsérée.

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

2. Créer un fichier `.env` à la racine du projet :

   ```env
   TAVILY_API_KEY=tvly-...
   OPENAI_API_KEY=sk-...
   ```

## Lancer l'application

Depuis la racine du projet :

```bash
uv run streamlit run src/projet_recherche_emploi/app.py
```

L'interface s'ouvre dans le navigateur, à l'adresse `http://localhost:8501`.

La commande doit être lancée depuis la racine : `cv.pdf`, `jobs.db` et `graph.png` sont cherchés ou créés dans le dossier courant.

## Utiliser l'interface

1. **Déposer son CV.** Dans la barre latérale, choisir un PDF puis cliquer sur « Enregistrer ce CV ». Il est enregistré à la racine sous le nom `cv.pdf` et remplace le précédent.
2. **Choisir les postes recherchés.** La barre latérale liste les recherches enregistrées. Chacune associe un type de contrat à une phrase de recherche, par exemple « offre d'emploi data engineer en CDI à Lyon ». Le formulaire en ajoute une, le bouton ✕ en supprime une. Elles sont conservées en base d'une session à l'autre.
3. **Lancer une recherche.** Le bouton « Lancer une recherche » est actif dès qu'un CV et au moins une recherche sont enregistrés. La page reste en attente pendant la recherche, qui peut prendre quelques minutes, puis indique le nombre de pages trouvées, d'offres retenues et de nouvelles offres en base.
4. **Suivre ses candidatures.** Le tableau liste les offres, de la plus récente à la plus ancienne, avec un lien vers l'annonce et la raison pour laquelle elle a été retenue. Cocher « Postulé » enregistre la candidature et sa date. Un filtre par type de contrat et un interrupteur masquant les offres déjà postulées sont disponibles au-dessus du tableau.

Chaque recherche consomme des crédits Tavily (une recherche avancée par poste recherché) et OpenAI (un appel par résultat, jusqu'à 20 par poste recherché).

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

Sans `APP_PASSWORD`, la page est ouverte à quiconque connaît l'adresse, et chaque recherche est facturée sur vos clés. Il est conseillé d'utiliser des clés dédiées à cette instance, avec un plafond de dépense.

Pour essayer l'image en local :

```bash
docker build -t recherche-emploi .
docker run -p 8501:8501 -v recherche-emploi-data:/data --env-file .env -e APP_PASSWORD=un-mot-de-passe recherche-emploi
```

## Fonctionnement

La recherche est un graph [LangGraph](https://langchain-ai.github.io/langgraph/) de trois étapes exécutées à la suite :

| Étape | Rôle |
|---|---|
| `searchJobs` | Lance une recherche Tavily par poste recherché enregistré, limitée aux sites d'emploi et aux annonces de la dernière semaine, puis supprime les doublons. |
| `FilterJobs` | Lit le CV (PDF) et demande à un modèle OpenAI, pour chaque résultat, si la page est une vraie offre (et non une liste d'offres) et si elle correspond au profil. |
| `InsertJobs` | Enregistre les offres retenues dans la base SQLite `jobs.db`. |

## Base de données

`jobs.db` contient deux tables, créées automatiquement.

Table `jobs`, les offres retenues :

| Colonne | Contenu |
|---|---|
| `url` | Lien de l'offre (identifiant unique) |
| `title` | Titre de la page |
| `content` | Extrait de l'annonce |
| `score` | Pertinence estimée par Tavily, entre 0 et 1 |
| `contract_type` | Type de contrat de la recherche qui a trouvé l'offre |
| `query` | Recherche qui a trouvé l'offre |
| `match_reason` | Justification du modèle pour avoir retenu l'offre |
| `applied` | `1` si vous avez postulé, `0` sinon |
| `applied_at` | Date de candidature (UTC), vide tant que vous n'avez pas postulé |
| `created_at` | Date d'insertion (UTC) |

Table `search_queries`, les postes recherchés :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la recherche |
| `contract_type` | Type de contrat (`CDI`, `freelance`, `CDD`, `alternance` ou `stage`) |
| `query` | Phrase envoyée à Tavily (unique) |
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

`DEFAULT_QUERIES` n'est utilisé qu'à la création de la base : une fois les recherches modifiées dans l'interface, il n'a plus d'effet.

## Structure du projet

```
src/projet_recherche_emploi/
├── app.py               # interface Streamlit
├── __init__.py          # point d'entrée de la commande projet-recherche-emploi
├── main.py              # construction du graph LangGraph
├── node.py              # les trois étapes : search_jobs, filter_jobs, insert_jobs
├── state.py             # état partagé entre les étapes
├── config.py            # réglages (chemins, modèle, recherches par défaut)
├── cv_reader.py         # lecture et enregistrement du CV en PDF
├── job_repository.py    # table des offres : insertion, lecture, suivi des candidatures
└── query_repository.py  # table des postes recherchés : lecture, ajout, suppression
```
