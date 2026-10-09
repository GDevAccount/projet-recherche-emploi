# Tamis

Tamis est un agent qui cherche des offres d'emploi sur le web, ne garde que celles qui correspondent à votre CV, et les enregistre dans une base SQLite. Une application web permet de déposer son CV, de choisir les postes recherchés, de lancer la recherche en la suivant en direct, et de suivre ses candidatures.

À chaque recherche, seules les nouvelles pages sont évaluées : une offre déjà en base (même URL) n'est pas réinsérée, et une page déjà rejetée n'est pas soumise à nouveau au modèle.

L'application tient en deux parties, servies par un seul processus et à une seule adresse : un serveur Python ([FastAPI](https://fastapi.tiangolo.com/)) qui porte l'[API](#api) et la recherche, et un [front Angular](#front-angular) qui n'appelle que cette API.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (il installe lui-même Python 3.11 si besoin)
- [Node.js](https://nodejs.org/) 22.22.3 ou plus récent, pour construire le front
- Une clé API [Tavily](https://tavily.com/)
- Une clé API [OpenAI](https://platform.openai.com/)
- Votre CV au format PDF, avec du texte sélectionnable (un PDF scanné sera refusé)

## Installation

1. Installer les dépendances du serveur, puis construire le front :

   ```bash
   uv sync
   cd frontend
   npm ci
   npm run build
   cd ..
   ```

2. Copier `.env.example` vers `.env` à la racine du projet, puis y renseigner les valeurs :

   ```env
   TAVILY_API_KEY=tvly-...
   OPENAI_API_KEY=sk-...
   APP_PASSWORD=un-mot-de-passe-long
   AUTH_COOKIE_SECRET=une-longue-chaîne-aléatoire
   ```

   `APP_PASSWORD` est le mot de passe que l'application demande, et `AUTH_COOKIE_SECRET` signe le cookie de session (`python -c "import secrets; print(secrets.token_hex(32))"` en fournit un). Les deux sont nécessaires, même en local : sans protection, l'API refuse toutes les requêtes. Pour plusieurs utilisateurs, voir [Connexion Google](#plusieurs-utilisateurs--connexion-google).

## Lancer l'application

Depuis la racine du projet :

```bash
uv run projet-recherche-emploi api
```

L'application s'ouvre à l'adresse `http://127.0.0.1:8000`, et la documentation de l'API à `http://127.0.0.1:8000/docs`.

La commande doit être lancée depuis la racine : `jobs.db` est cherché ou créé dans le dossier courant, et le front construit dans `frontend/dist/`. Sans ce build, seule l'API répond.

## Utiliser l'application

L'application a trois rubriques, **Offres**, **Rejets** et **Profil**, un thème sombre, que le bouton de l'en-tête passe au clair, et un bouton « Lancer une recherche » visible partout.

1. **Déposer son CV.** Dans la rubrique Profil, glisser un PDF sur la carte « CV », ou cliquer pour le choisir, puis « Enregistrer ce CV ». Seul son texte est gardé, sans vos coordonnées : le fichier n'est pas conservé. Il remplace le précédent. Les pages rejetées avec l'ancien CV sont alors oubliées : elles seront réévaluées à la prochaine recherche.
2. **Choisir les postes recherchés.** La carte « Postes recherchés » liste les recherches enregistrées. Chacune associe un type de contrat à une phrase de recherche, par exemple « ingénieur IA générative LLM RAG », et à un lieu : une ville, un département ou une région, « télétravail complet », ou toute la France. La phrase envoyée au moteur de recherche est précédée de « offre d'emploi » et suivie du type de contrat et du lieu, sauf si elle les contient déjà : sans ces mots, une phrase courte ramène des listes d'offres plutôt que des annonces. Une recherche en télétravail complet est lancée deux fois : en français sur les sites d'emploi habituels, puis en anglais (« AI engineer remote job ») sur ces sites et sur des sites d'offres en télétravail à l'international. Elle consomme donc deux recherches Tavily. La phrase nomme le métier visé, suivi de ses spécialités : le filtre ne retient que les offres de l'un des métiers recherchés, même si le CV en couvre d'autres. Une phrase qui ne cite qu'une technologie (« langchain langgraph ») ne dit pas quel métier retenir : préférer « développeur d'agents IA LangChain LangGraph ». Pour trouver aussi les annonces rédigées en anglais, enregistrer une seconde recherche avec l'intitulé anglais. Une offre est retenue si son lieu de travail convient à l'une au moins des recherches enregistrées : une recherche pour toute la France ouvre donc tout le pays, et « télétravail complet » ne retient que les postes 100 % à distance, que l'employeur soit en France ou à l'étranger, sauf si l'annonce réserve le poste aux résidents d'un autre pays. Sans recherche « télétravail complet », un poste à distance n'est retenu que si l'employeur se trouve dans l'un des lieux recherchés. Le formulaire en ajoute une, la croix en supprime une.
3. **Lancer une recherche.** Le bouton « Lancer une recherche » apparaît dès qu'un CV et au moins une recherche sont enregistrés. Un panneau suit alors la recherche en direct, ce qui peut prendre quelques minutes : les quatre étapes du graph, le nombre de pages trouvées, à évaluer, évaluées, retenues et écartées, et un journal où chaque page évaluée apparaît avec son verdict. Il se termine par le nombre de nouvelles offres. Fermer la page n'arrête pas la recherche : elle va au bout sur le serveur.
4. **Suivre ses candidatures.** La rubrique Offres range les offres selon l'état de la candidature. Les entretiens sont en tête, mis en avant. Viennent ensuite deux colonnes, « À traiter » et « Postulées », de la plus récente à la plus ancienne, puis les candidatures refusées, repliées en bas de page. Chaque carte donne le site, le titre, le contrat et le lieu que le modèle a lus sur l'annonce (ou « non précisé » si elle ne le dit pas), et la raison pour laquelle l'offre a été retenue. Le lieu vaut « Remote » pour un poste en télétravail complet, par exemple « Remote (Los Angeles, États-Unis) ». « J'ai postulé » puis « Entretien obtenu » font avancer une candidature, et chaque étape est datée ; la flèche de retour corrige une erreur, et un glisser-déposer d'une zone à l'autre fait la même chose. Au-dessus, des chiffres clés, un champ de recherche (sur le titre, le lieu et la raison, par exemple pour retrouver une entreprise ou une ville) et un filtre par contrat.
5. **Classer un refus, ou supprimer une offre.** La corbeille d'une carte ouvre une fenêtre qui demande quoi faire de l'offre. « L'employeur a refusé ma candidature », proposé une fois la candidature envoyée, la range dans les candidatures refusées, d'où elle peut être rouverte. « Supprimer cette annonce » la retire : une offre supprimée ne revient pas aux recherches suivantes.
6. **Comprendre les rejets.** La rubrique Rejets montre d'abord la répartition des pages écartées par motif, puis leur liste, avec la raison donnée. Le motif est le premier critère en défaut : pour une page qui n'est pas une offre, sa nature (« Liste ou page de résultats », « Article », « Fiche métier », « Page d'accueil », « Offre expirée », ou « Pas une offre valable » pour le reste et pour les pages écartées avant ce détail) ; pour une offre, « Autre métier que ceux recherchés », « Contrat non recherché » (stage ou alternance qu'aucune recherche ne demande, et aussi une page de formation), « Compétences insuffisantes », « Niveau d'expérience incompatible » ou « Hors lieu recherché ». Les autres critères en défaut suivent, après « aussi ». Les pages rejetées avant ce détail gardent le motif « Hors profil ». Ajouter une recherche fait oublier les rejets dus au métier, au contrat ou au lieu : ces pages seront réévaluées si elles sont retrouvées. Cliquer sur un motif ne garde que ses pages ; un filtre par recherche d'origine et un champ de recherche aident à repérer ce qui fait perdre des offres.
7. **Suivre les coûts (administrateurs).** La rubrique Suivi n'apparaît qu'au propriétaire et aux adresses d'`ADMIN_EMAILS`. Elle donne le coût total des recherches et le coût par offre retenue, la part de Tavily et d'OpenAI, ce que deviennent les pages évaluées (par poste recherché, par site, par nature de page, selon le texte lu), la liste des recherches avec, pour chacune, ses mesures et chaque page évaluée, et la consommation de chaque compte sur 30 jours, 90 jours ou depuis le début.

Chaque recherche consomme des crédits Tavily (une recherche avancée par poste recherché) et OpenAI (un appel par résultat qui n'a pas déjà été évalué, jusqu'à 20 par poste recherché).

Un schéma du graph peut être généré dans `graph.png` avec `uv run projet-recherche-emploi graph`. Il est produit par le service en ligne mermaid.ink, donc une connexion internet est nécessaire.

### En ligne de commande

La recherche seule peut aussi être lancée en ligne de commande, avec le CV et les recherches déjà enregistrés :

```bash
uv run projet-recherche-emploi
```

La même commande a d'autres usages :

| Commande | Effet |
|---|---|
| `uv run projet-recherche-emploi` (ou `search`) | Lance une recherche pour le propriétaire |
| `uv run projet-recherche-emploi graph` | Génère le schéma du graph dans `graph.png` |
| `uv run projet-recherche-emploi migrate` | Crée la base ou l'amène à la dernière version du schéma |
| `uv run projet-recherche-emploi purge` | Supprime les comptes d'invités inactifs depuis trop longtemps. Le serveur le fait aussi, une fois par jour |
| `uv run projet-recherche-emploi api` | Sert l'application en développement sur `http://127.0.0.1:8000`, avec la documentation de l'[API](#api) |
| `uv run projet-recherche-emploi serve` | Sert l'application en ligne, sur le port 8000 de toutes les interfaces, sans la documentation de l'API |

## API

Tout ce que fait le front passe par cette API, sous `/api`. Un script peut l'appeler de la même façon.

La documentation interactive est à l'adresse `http://127.0.0.1:8000/docs`, et le schéma OpenAPI à `http://127.0.0.1:8000/openapi.json`, avec la commande `api`. La commande `serve`, utilisée en ligne, ne les sert pas : rien n'y décrit les routes à qui n'est pas connecté.

| Route | Rôle |
|---|---|
| `GET /api/health` | État du serveur (sans connexion) |
| `GET /api/config` | Ce qu'un front lit avant la connexion (sans connexion) : mode de connexion (`google` ou `password`), identifiant client Google, types de contrat, motifs proposés à la suppression d'une offre (`delete_reasons`) |
| `GET /api/me` | Utilisateur de la requête (avec l'adresse, le nom et la photo de son compte Google), s'il est propriétaire (`is_owner`) ou administrateur (`is_admin`), recherches restantes aujourd'hui, s'il peut lancer une recherche (`can_search` : un CV et au moins un poste recherché), et si l'une des siennes tourne déjà (`search_running`) |
| `DELETE /api/me` | Supprimer son compte : CV, postes recherchés, offres, rejets, lancements, journal des pages évaluées, appels au moteur de recherche, corrections du tri et adresse sont effacés ; seule sa consommation reste, en totaux mensuels sans adresse (table `archived_usage`). Ils sont effacés, y compris dans les copies d'avant migration, qui restent. Refusé (409) pendant une recherche |
| `POST /api/session`, `DELETE /api/session` | Ouvrir une session (cookie), la fermer |
| `GET /api/jobs` | Offres retenues |
| `PATCH /api/jobs/{id}` | Changer l'état d'une candidature (`{"status": "applied"}` ; `todo`, `applied`, `interview` ou `rejected`). Renvoie l'offre mise à jour, avec la date de chaque étape et les états qu'elle peut prendre ensuite (`next_statuses`). Un état que l'offre ne peut pas prendre depuis le sien est refusé (422) |
| `DELETE /api/jobs/{id}` | Supprimer une offre. `?reason=` en donne le motif, facultatif, parmi ceux de `/api/config` (`not_my_job`, `profile`, `location`, `contract`, `not_an_offer`, `not_interested`) ; un autre est refusé (422). La suppression est enregistrée dans `corrections` |
| `GET /api/rejected-jobs` | Pages rejetées, avec leur motif (`motive`) et tous les critères en défaut (`failed_criteria`) |
| `POST /api/rejected-jobs/restore` | Remettre une page rejetée dans les offres (`{"url": "…"}`) : elle devient une offre à traiter, son rejet est oublié et la correction enregistrée dans `corrections`. Renvoie l'offre créée. 404 si la page n'est pas parmi les rejets, 409 si son adresse est déjà celle d'une offre |
| `GET /api/queries`, `POST /api/queries`, `DELETE /api/queries/{id}` | Postes recherchés |
| `GET /api/cv`, `PUT /api/cv` | Date du CV en place, dépôt d'un CV (fichier PDF, champ `file`) |
| `POST /api/searches` | Lancer une recherche, suivie en direct (Server-Sent Events : `progress`, puis `result` ou `error`). Chaque `progress` nomme son étape (`step` : `search`, `dedupe`, `evaluate` ou `save`) et porte, selon l'étape, un décompte (`done`, `total`), le nombre de pages trouvées et à évaluer (`found`, `new`), ou la page qui vient d'être évaluée et son verdict (`title`, `kept`). Refusé (409) si une recherche de l'utilisateur tourne déjà |
| `GET /api/searches` | Réservée aux administrateurs (le propriétaire et `ADMIN_EMAILS` ; 403 pour un invité), comme les trois suivantes. Les 100 derniers lancements de l'appelant, avec leur bilan : état (`status` : `running`, `done`, `failed` ou `interrupted`), compteurs, durée totale (`duration_ms`) et de chaque étape en millisecondes, appels au moteur de recherche, jetons du modèle, modèle et version du prompt |
| `GET /api/searches/stats` | Synthèse de toutes les recherches suivies de l'appelant : volumes, jetons, coût en dollars (moteur de recherche, modèle, total, par offre retenue), durée moyenne, et répartition des pages évaluées par poste recherché (`by_query`), par site (`by_site`), par nature (`by_page_kind`) et selon le texte lu (`by_text` : page entière, page tronquée, extrait seul). `by_search` donne le rendement de chaque texte envoyé au moteur de recherche, le moins rentable en premier : appels, pages rendues, en double dans le lancement (`repeated`), déjà connues (`known`), évaluées puis écartées (`rejected`), retenues (`kept`), coût des appels et coût par offre retenue. `corrections` compte, par version du prompt, les pages écartées remises dans les offres et les offres supprimées en reprochant quelque chose au tri, avec leurs taux ; `delete_reasons` compte les suppressions par motif |
| `GET /api/searches/{id}/evaluations` | Pages évaluées pendant un lancement, retenues ou non : faits lus par le modèle, avis et règles du verdict, longueur du texte lu, jetons et durée de l'appel |
| `GET /api/admin/usage` | Consommation de tous les comptes, le plus coûteux en premier : pour chacun, son adresse, ses lancements, ses appels, ses jetons et son coût en dollars et sa formule (`plan`, `free` tant qu'il n'y a pas de paiement) ; puis le total, et la part due aux invités (`guests_cost_usd`). Un compte supprimé y reste, sans adresse (`deleted`), avec ce qu'il avait consommé. `?days=30` limite le calcul aux derniers jours. Aucune page ni recherche d'un autre compte n'en sort |

L'appelant prouve son identité par un en-tête `Authorization: Bearer <jeton>`. La règle :

- **avec la connexion Google** (`GOOGLE_CLIENT_ID` défini), le jeton est un jeton d'identité Google émis pour cet identifiant client. L'adresse qu'il porte désigne l'utilisateur, selon `OWNER_EMAIL` et `ALLOWED_EMAILS` ;
- **sans elle**, le jeton est `APP_PASSWORD`, et désigne le propriétaire ;
- **sans aucun des deux**, l'API refuse toutes les requêtes (code 503) : elle ne s'ouvre jamais sans protection, même en local.

Un script peut envoyer cet en-tête à chaque requête. Un navigateur ne l'envoie qu'une fois, à `POST /api/session`, qui répond par un cookie `session` valable 30 jours ; les requêtes suivantes n'ont plus besoin d'en-tête. Le jeton Google n'est en effet valable qu'une heure, et ce cookie est illisible pour le JavaScript de la page (`HttpOnly`), donc hors de portée d'un script injecté. `DELETE /api/session` le supprime.

- Le cookie est signé avec `AUTH_COOKIE_SECRET`, qui doit donc être défini, même sans connexion Google. Changer ce secret, ou `APP_PASSWORD`, ferme toutes les sessions.
- Il porte l'adresse Google, pas un droit d'accès : retirer une adresse de `ALLOWED_EMAILS` ferme ses sessions au redémarrage.
- Il n'est envoyé qu'en HTTPS, sauf sur `localhost`, et jamais à la demande d'un autre site (`SameSite=Strict`). Une requête qui modifie des données est en plus refusée (403) si son en-tête `Origin` n'est ni l'adresse de l'API ni une origine de `CORS_ORIGINS`.
- Une session ne se prolonge pas : au bout de 30 jours, le front redemande une connexion.

Un navigateur ne peut appeler l'API depuis un autre site que si son origine figure dans `CORS_ORIGINS`. Le front n'en a pas besoin : il est servi à la même adresse que l'API.

Les erreurs ont la forme `{"detail": "message en français"}`, avec le code 422 (demande refusée), 404 (élément inconnu), 409 (doublon), 429 (quota atteint) ou 503 (instance mal réglée).

## Front Angular

Le front est une application [Angular](https://angular.dev/) 22, avec les composants [PrimeNG](https://primeng.org/). Il est dans `frontend/`, n'appelle que l'API, et ne contient aucune règle métier : ce qu'un écran affiche de calculé vient du serveur.

```bash
cd frontend
npm ci                 # installer les dépendances
npm start              # serveur de développement : http://localhost:4200
npm test               # tests (Vitest)
npm run lint           # linter (ESLint)
npm run build          # build de production, dans frontend/dist/
npm run e2e            # tests de bout en bout (Playwright), après un build
```

`npm start` recharge la page à chaque modification, et relaie les appels à `/api` vers `http://127.0.0.1:8000` (`proxy.conf.json`) : lancer le serveur à côté avec `uv run projet-recherche-emploi api`. Le navigateur ne voit ainsi qu'une seule adresse, comme en ligne, et `CORS_ORIGINS` reste inutile.

Une fois le front construit par `npm run build`, le serveur Python le sert lui-même à la racine du site. L'image Docker fait ce build dans une première étape : elle ne contient ni Node ni `node_modules`.

PrimeNG demande une clé de licence, gratuite pour un particulier ou une petite structure (licence « Community », à demander sur <https://primeui.dev/pricing>, valable un an et renouvelable). Sans elle, le front fonctionne mais affiche un bandeau « licence invalide ». Le dépôt étant public, la clé n'y est pas écrite : elle est passée au build.

```bash
npm start -- --define "PRIMEUI_LICENSE='ma-clé'"         # en développement
npm run build -- --define "PRIMEUI_LICENSE='ma-clé'"     # build de production
fly deploy --build-arg PRIMEUI_LICENSE=ma-clé             # publication à la main
```

Le workflow de déploiement la lit dans le secret `PRIMEUI_LICENSE` du dépôt GitHub (**Settings → Secrets and variables → Actions**). Elle se retrouve dans le JavaScript servi aux visiteurs : ce n'est pas un secret au sens des clés API, seulement une valeur qu'on évite de publier dans le dépôt.

L'adresse de l'API est dans `frontend/src/environments/` (`apiUrl`, par défaut `/api`), jamais dans le code. Pour héberger le front ailleurs, y mettre l'adresse complète de l'API et déclarer l'adresse du front dans `CORS_ORIGINS`.

## Héberger l'application pour quelqu'un d'autre

Pour qu'une personne l'utilise sans rien installer, l'application peut tourner sur un serveur : elle l'ouvre dans son navigateur, et les clés API restent sur le serveur. Sans connexion Google, une instance sert une seule personne (un CV, une base).

Le `Dockerfile` fourni construit l'image, front compris. L'hébergeur doit proposer un volume persistant, sinon le CV et la base sont perdus à chaque redémarrage.

| À régler chez l'hébergeur | Valeur |
|---|---|
| Variable `TAVILY_API_KEY` | Clé Tavily |
| Variable `OPENAI_API_KEY` | Clé OpenAI |
| Variable `APP_PASSWORD` | Mot de passe demandé à la connexion |
| Variable `AUTH_COOKIE_SECRET` | Longue chaîne aléatoire, qui signe le cookie de session |
| Volume persistant | Monté sur `/data` |
| Port exposé | `8000` |

Avec un mot de passe ou la connexion Google mais sans `AUTH_COOKIE_SECRET`, l'application refuse de démarrer : aucune session ne pourrait s'ouvrir. Les précautions à prendre sont détaillées dans [Sécurité](#sécurité).

Pour essayer l'image en local :

```bash
docker build -t recherche-emploi .
docker run -p 8000:8000 -v recherche-emploi-data:/data --env-file .env recherche-emploi
```

### Instance déployée sur Fly.io

Le projet est déployé sur [Fly.io](https://fly.io/), à l'adresse <https://projet-recherche-emploi.fly.dev/>. La configuration est dans `fly.toml`.

Cette instance demande une connexion Google, réservée aux adresses invitées : pour la tester, le demander à l'auteur.

À faire une seule fois, avant le premier déploiement :

```bash
fly scale count 1                                # une seule machine : un volume n'est pas partagé entre machines
fly volumes create data --region cdg --size 1    # volume monté sur /data (CV et base)
fly secrets set TAVILY_API_KEY=... OPENAI_API_KEY=... APP_PASSWORD=... AUTH_COOKIE_SECRET=...
```

Une nouvelle version est publiée automatiquement à chaque push sur la branche `main`, par le workflow GitHub Actions `.github/workflows/fly-deploy.yml`. Il lance d'abord le linter et les tests, côté Python et côté front, puis le build du front et les tests de bout en bout : si l'un échoue, rien n'est publié. Il les lance aussi sur chaque pull request, sans rien publier. Le déroulement se suit dans l'onglet **Actions** du dépôt. L'instance redémarre à chaque déploiement : le volume `/data` est conservé, mais une recherche en cours est interrompue.

Sans visite, la machine est mise en veille (`auto_stop_machines = 'suspend'` dans `fly.toml`) : elle ne coûte rien pendant ce temps et reprend en une seconde à la visite suivante, sans redémarrer. Un vrai démarrage, de plusieurs secondes, n'a lieu qu'après un déploiement ou si Fly.io a dû écarter son instantané.

Ce workflow lit aussi la clé de licence PrimeNG dans le secret `PRIMEUI_LICENSE` (voir [Front Angular](#front-angular)). Il a besoin d'un jeton Fly.io, enregistré une seule fois comme secret `FLY_API_TOKEN` du dépôt GitHub :

```bash
fly tokens create deploy -x 999999h    # jeton limité à cette application
gh secret set FLY_API_TOKEN            # coller le jeton, préfixe « FlyV1 » compris
```

Pour publier à la main, sans passer par GitHub, ni donc par les tests :

```bash
fly deploy --build-arg PRIMEUI_LICENSE=ma-clé
```

Pour changer le mot de passe (la machine redémarre avec la nouvelle valeur) :

```bash
fly secrets set APP_PASSWORD=nouveau-mot-de-passe
```

## Plusieurs utilisateurs : connexion Google

Par défaut, l'application sert une seule personne, protégée par `APP_PASSWORD`. En activant la connexion Google, chaque personne invitée se connecte avec son compte Google et dispose de son propre CV, de ses recherches, de ses offres et de ses pages rejetées.

- **Le propriétaire** (`OWNER_EMAIL`) retrouve les données existantes et n'a pas de limite de recherches.
- **Les invités** (`ALLOWED_EMAILS`) partent d'un compte vide et ont droit à 2 recherches par jour (le compteur repart à minuit, heure de Paris). Toutes les recherches sont facturées sur les clés API du propriétaire.
- **Toute autre adresse** est refusée, même connectée à Google.
- **Ouverture à tous** : avec `ALLOWED_EMAILS=*`, tout compte Google peut se connecter et reçoit un compte d'invité. Chaque nouvel inscrit peut alors lancer 2 recherches par jour sur vos clés API : fixer d'abord un plafond de dépense chez Tavily et OpenAI.

Quand la connexion Google est active, `APP_PASSWORD` n'est plus demandé.

### 1. Créer l'identifiant Google

Dans la [console Google Cloud](https://console.cloud.google.com/apis/credentials), créer un « ID client OAuth » de type « Application Web », avec comme « origines JavaScript autorisées », sans barre oblique finale :

- `https://projet-recherche-emploi.fly.dev` pour l'instance en ligne ;
- `http://localhost:4200` et `http://localhost:8000` pour un essai en local, avec `npm start` ou avec le serveur seul.

Google fournit alors un identifiant client. Le front s'en sert pour afficher le bouton « Se connecter avec Google », et le serveur pour vérifier le jeton que ce bouton renvoie : aucun code secret ni URI de redirection n'est nécessaire. Tant que l'écran de consentement est en mode « Test », seules les adresses ajoutées comme utilisateurs de test peuvent se connecter.

Pour passer en mode « En production », Google demande deux liens, que l'application sert sans connexion :

- règles de confidentialité : `https://projet-recherche-emploi.fly.dev/confidentialite`
- conditions d'utilisation : `https://projet-recherche-emploi.fly.dev/conditions`

Ce sont des pages HTML simples, lisibles par les robots de Google, qui ne voient pas le contenu d'une page construite en JavaScript. Leurs textes sont dans `src/projet_recherche_emploi/api/legal/`. Ils décrivent ce que fait l'application telle qu'elle est : les relire, et les tenir à jour si elle change. Même en production, seules les adresses de `OWNER_EMAIL` et `ALLOWED_EMAILS` accèdent à l'application, sauf si `ALLOWED_EMAILS` vaut `*`.

Google peut aussi demander la preuve que le site vous appartient. Dans [Search Console](https://search.google.com/search-console), ajouter une propriété de type « Préfixe de l'URL » avec l'adresse de l'instance, choisir la méthode « Fichier HTML », et mettre le nom du fichier proposé dans `GOOGLE_SITE_VERIFICATION_FILE` : l'application le sert alors à la racine du site, sans qu'il faille le déposer.

### 2. Renseigner les variables

| Variable | Valeur |
|---|---|
| `GOOGLE_CLIENT_ID` | Identifiant client fourni par Google |
| `AUTH_COOKIE_SECRET` | Chaîne aléatoire longue, qui signe le cookie de session (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `OWNER_EMAIL` | Adresse Google du propriétaire |
| `ALLOWED_EMAILS` | Adresses des invités, séparées par des virgules (peut être vide), ou `*` pour accepter tout compte Google |
| `ADMIN_EMAILS` | Adresses des administrateurs, séparées par des virgules (facultatif). Comme le propriétaire, ils ont accès au suivi des recherches et à la consommation de chaque compte. Un administrateur peut se connecter sans figurer dans `ALLOWED_EMAILS` ; il garde un compte d'invité, avec son quota |
| `CONTACT_EMAIL` | Adresse de contact affichée sur les deux pages publiques (facultatif, mais attendu par le RGPD) |
| `GOOGLE_SITE_VERIFICATION_FILE` | Nom du fichier de validation donné par Google Search Console, par exemple `google1a2b3c.html` (facultatif) |

Les trois premières vont ensemble : avec `GOOGLE_CLIENT_ID` mais sans `OWNER_EMAIL` ou sans `AUTH_COOKIE_SECRET`, l'application refuse de démarrer plutôt que de s'ouvrir sans la connexion attendue.

En ligne, ce sont des secrets Fly.io (la machine redémarre avec les nouvelles valeurs) :

```bash
fly secrets set GOOGLE_CLIENT_ID=... AUTH_COOKIE_SECRET=... OWNER_EMAIL=... ALLOWED_EMAILS=...
```

Pour inviter ou retirer quelqu'un, relancer `fly secrets set ALLOWED_EMAILS=...` avec la liste complète. Une personne retirée ne peut plus se connecter ; ses données restent en base.

En local, les mettre dans `.env` et relancer le serveur. Pour revenir au mot de passe unique, vider `GOOGLE_CLIENT_ID`.

## Sécurité

Sans connexion Google, la seule protection est le mot de passe unique `APP_PASSWORD`. Quiconque le connaît peut lire et remplacer le CV, modifier les recherches et lancer des recherches facturées sur vos clés. Avec la connexion Google, l'accès est limité aux adresses invitées, et chaque invité ne voit que ses propres données.

- **Toujours définir `APP_PASSWORD` ou la connexion Google sur une instance en ligne.** Sans l'un des deux, l'application ne s'ouvre à personne. Une session dure 30 jours, puis la connexion est redemandée.
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
| `FilterJobs` | Lit le texte du CV, enregistré sans coordonnées, et demande à un modèle OpenAI, pour chaque page restante, ce qu'elle dit (sa nature : offre, liste d'offres, article, fiche métier, page d'accueil, offre expirée, formation ou autre ; contrat, lieu, mode de travail) et trois avis : le métier est-il l'un de ceux des recherches enregistrées, le CV couvre-t-il les compétences principales, le niveau d'expérience est-il compatible. Le graph applique ensuite les règles de contrat et de lieu : une offre n'est retenue que si tous les critères sont remplis. |
| `InsertJobs` | Enregistre les offres retenues et les pages rejetées dans la base SQLite `jobs.db`. |

## Base de données

`jobs.db` contient cinq tables, créées et tenues à jour par des migrations [Alembic](https://alembic.sqlalchemy.org/) que l'application applique seule à son démarrage (voir [Faire évoluer le schéma](#faire-évoluer-le-schéma)). Une sixième, `alembic_version`, retient la version du schéma. Le code y accède avec [SQLAlchemy](https://www.sqlalchemy.org/).

Table `jobs`, les offres retenues :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de l'offre, par lequel l'API la désigne |
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `url` | Lien de l'offre (unique par utilisateur) |
| `title` | Titre de la page |
| `content` | Extrait de l'annonce |
| `score` | Pertinence estimée par Tavily, entre 0 et 1 |
| `contract_type` | Type de contrat lu sur l'annonce par le modèle, vide si elle ne le dit pas. Pour les offres trouvées avant ce changement : celui de la recherche qui a trouvé l'offre |
| `work_location` | Ville lue sur l'annonce par le modèle, suivie du pays hors de France. Pour un poste en télétravail complet : `Remote`, suivi entre parenthèses de la ville de l'employeur si l'annonce la donne. Vide si l'annonce ne le dit pas, et pour les offres trouvées avant l'ajout de la colonne |
| `query` | Recherche qui a trouvé l'offre |
| `match_reason` | Justification du modèle pour avoir retenu l'offre |
| `status` | État de la candidature : `todo` (à traiter), `applied` (postulée), `interview` (entretien obtenu) ou `rejected` (refusée par l'employeur) |
| `applied_at` | Date de candidature (UTC), vide tant que vous n'avez pas postulé |
| `interview_at` | Date à laquelle l'entretien a été noté (UTC), vide sans entretien |
| `rejected_at` | Date à laquelle le refus a été noté (UTC), vide sans refus |
| `created_at` | Date d'insertion (UTC) |
| `deleted` | `1` si vous avez supprimé l'offre : elle n'est plus affichée, mais sa ligne reste pour qu'elle ne soit pas réinsérée |

Table `rejected_jobs`, les pages rejetées par le modèle. Elle sert à ne pas payer une nouvelle évaluation pour une page déjà rejetée. Elle est vidée quand un nouveau CV est enregistré.

| Colonne | Contenu |
|---|---|
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `url` | Lien de la page (unique par utilisateur) |
| `title` | Titre de la page |
| `contract_type` | Type de contrat lu sur la page par le modèle, souvent vide. Pour les pages rejetées avant ce changement : celui de la recherche qui a trouvé la page |
| `work_location` | Ville lue sur la page par le modèle, ou `Remote`, souvent vide |
| `query` | Recherche qui a trouvé la page |
| `is_real_offer` | `1` si le modèle y a vu une vraie offre, `0` sinon |
| `page_kind` | Nature de la page selon le modèle : `offre`, `liste d'offres`, `article`, `fiche métier`, `page d'accueil`, `offre expirée`, `formation` ou `autre`. Vide pour les pages rejetées avant son ajout |
| `matches_cv` | `1` si le modèle a jugé que le poste correspond au CV (compétences et niveau), `0` sinon |
| `matches_search` | `0` si le métier du poste n'est aucun de ceux recherchés, `1` sinon |
| `matches_contract` | `0` pour un stage ou une alternance qu'aucune recherche ne demande, `1` sinon |
| `matches_skills` | `0` si le CV ne couvre pas les compétences principales du poste, `1` sinon |
| `matches_level` | `0` si le niveau d'expérience est manifestement incompatible, `1` sinon |
| `matches_location` | `0` si le lieu de travail ne fait partie d'aucun lieu recherché, `1` sinon. Ces cinq colonnes de détail sont vides pour les pages rejetées avant leur ajout, quand une offre hors Île-de-France était classée « pas une offre » |
| `reject_reason` | Justification du modèle pour avoir rejeté la page |
| `created_at` | Date du rejet (UTC) |

Table `search_queries`, les postes recherchés :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la recherche |
| `user_id` | Utilisateur propriétaire de la ligne. Vaut `1` tant que l'application n'a qu'un utilisateur |
| `contract_type` | Type de contrat (`CDI`, `freelance`, `CDD`, `alternance` ou `stage`) |
| `query` | Phrase envoyée à Tavily, complétée du type de contrat et du lieu. Le trio phrase, lieu et télétravail est unique par utilisateur |
| `location` | Ville, département ou région visés. Vide : toute la France. Les recherches d'avant cette colonne ont reçu `Île-de-France`, que le filtre imposait alors |
| `remote` | `1` pour ne retenir que le télétravail complet, sans condition de lieu, `0` sinon |
| `created_at` | Date d'ajout (UTC) |

Table `users`, les comptes (connexion Google) :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant du compte. Le `1` est réservé au propriétaire |
| `email` | Adresse Google de l'invité (vide pour le propriétaire, dont l'adresse vient de `OWNER_EMAIL`) |
| `created_at` | Date de la première connexion (UTC) |
| `last_seen_at` | Date de la dernière requête identifiée (UTC), au jour près. Un compte d'invité sans activité depuis `INACTIVE_ACCOUNT_DAYS` est supprimé |

Table `cv_texts`, le texte du CV de chaque utilisateur, coordonnées retirées. C'est tout ce que l'application garde d'un CV : le PDF déposé est lu une fois, puis oublié. Ce texte est envoyé à OpenAI par le filtre, sa date dit depuis quand le CV est en place, et il est remplacé à chaque dépôt :

| Colonne | Contenu |
|---|---|
| `user_id` | Compte auquel appartient ce texte |
| `content` | Texte du CV, où e-mail, téléphone, liens, adresse postale, date de naissance et nom du compte sont remplacés par une étiquette (`[e-mail]`, `[téléphone]`…) |
| `updated_at` | Date de l'enregistrement (UTC) |

Table `search_runs`, les lancements de recherche. Ils servent au quota journalier, et gardent le bilan de chaque recherche. Tout sauf la date est vide pour les lancements d'avant ce suivi :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant du lancement |
| `user_id` | Utilisateur qui a lancé la recherche |
| `created_at` | Date du lancement (UTC) |
| `status` | `running` au lancement, puis `done` ou `failed`. Un lancement coupé par un redémarrage du serveur reste `running` : l'API le dit `interrupted` |
| `error` | Type de l'erreur d'une recherche échouée (`RateLimitError`…), sans son message, qui reste dans les logs |
| `finished_at` | Date de fin (UTC) |
| `model`, `prompt_version` | Modèle interrogé, et empreinte du prompt du filtre : elle change dès qu'un mot de ses consignes change |
| `found_count`, `new_count`, `kept_count`, `rejected_count`, `inserted_count` | Pages trouvées, nouvelles, retenues, rejetées, et offres réellement insérées |
| `search_ms`, `dedupe_ms`, `evaluate_ms`, `save_ms` | Durée de chaque étape du graph, en millisecondes |
| `search_calls` | Nombre d'appels à Tavily |
| `input_tokens`, `output_tokens` | Jetons envoyés au modèle et reçus de lui, toutes pages confondues |
| `cache_read_tokens`, `cache_write_tokens` | Parts des jetons d'entrée lues ou écrites en cache, facturées à un autre tarif |
| `reasoning_tokens` | Part des jetons de sortie passée en raisonnement, que la réponse ne montre pas |

Table `page_evaluations`, le journal des pages évaluées, retenues ou non. Contrairement à `rejected_jobs`, il n'est pas vidé quand un nouveau CV est enregistré :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la ligne |
| `user_id` | Utilisateur propriétaire de la ligne |
| `search_run_id` | Lancement pendant lequel la page a été évaluée |
| `url`, `title`, `query`, `score` | La page, la recherche qui l'a trouvée et le score donné par Tavily |
| `kept` | `1` si la page a été retenue, `0` si elle a été rejetée |
| `page_kind`, `contract_type`, `work_city`, `work_country`, `work_mode` | Faits lus sur la page par le modèle |
| `in_accepted_area`, `open_to_candidates_in_france` | Ce que le modèle a répondu sur le lieu, dont le graph tire `matches_location` |
| `matches_search`, `matches_skills`, `matches_level` | Avis du modèle |
| `matches_contract`, `matches_location` | Règles appliquées par le graph |
| `reason` | Justification écrite par le modèle |
| `page_chars`, `truncated` | Longueur du texte disponible, et `1` si le modèle n'en a lu que le début (au-delà de `MAX_PAGE_CHARS`) |
| `full_page` | `1` si le texte complet de la page était disponible, `0` si seul l'extrait de Tavily a été lu |
| `input_tokens`, `output_tokens`, `duration_ms` | Jetons et durée de l'appel au modèle pour cette page |
| `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens` | Détail de ces jetons, comme pour un lancement |
| `created_at` | Date de l'enregistrement (UTC) |

Table `engine_calls`, une ligne par appel au moteur de recherche et par lancement. Elle est écrite à la fin du lancement, même s'il échoue :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la ligne |
| `user_id` | Utilisateur propriétaire de la ligne |
| `search_run_id` | Lancement pendant lequel l'appel a été fait |
| `query`, `search_text` | Phrase saisie par l'utilisateur, et texte réellement envoyé au moteur |
| `international` | `1` pour la variante en anglais d'une recherche en télétravail complet |
| `found_count` | Pages rendues par l'appel |
| `unique_count` | Parmi elles, celles qu'aucun appel précédent du lancement n'avait déjà rendues |
| `new_count` | Parmi celles-là, les pages encore inconnues, donc évaluées ; vide si le lancement s'est arrêté avant |
| `kept_count` | Parmi celles-là, les offres retenues ; vide si le lancement s'est arrêté avant |
| `duration_ms` | Durée de l'appel |
| `created_at` | Date de l'enregistrement (UTC) |

Table `corrections`, ce que l'utilisateur a corrigé du tri. Une ligne par page écartée remise dans les offres et par offre supprimée :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la ligne |
| `user_id` | Utilisateur propriétaire de la ligne |
| `kind` | `restored` pour une page écartée remise dans les offres, `deleted` pour une offre supprimée |
| `url`, `title`, `query` | La page, et la recherche qui l'avait trouvée |
| `reason` | Motif choisi à la suppression ; vide s'il n'a pas été précisé, et pour une page remise |
| `page_kind`, `matches_search`, `matches_contract`, `matches_skills`, `matches_level`, `matches_location` | Verdict contredit d'une page écartée ; vides pour une offre supprimée |
| `model_reason` | Justification que le modèle avait donnée |
| `search_run_id`, `model`, `prompt_version` | Lancement qui avait évalué la page, son modèle et son prompt ; vides si le journal ne connaît pas la page |
| `created_at` | Date de la correction (UTC) |

Table `archived_usage`, la consommation des comptes supprimés. Elle est écrite à la suppression d'un compte, juste avant l'effacement de ses lancements, et n'est jamais vidée :

| Colonne | Contenu |
|---|---|
| `id` | Identifiant de la ligne |
| `account_id` | Ancien identifiant du compte : il ne désigne plus personne, sa ligne de `users` n'ayant plus d'adresse |
| `plan` | Formule du compte à sa suppression (`free` ou `paid`) |
| `month` | Mois des lancements additionnés (`AAAA-MM`) : la date précise des recherches n'est pas gardée |
| `model` | Modèle interrogé, dont le tarif dépend |
| `runs`, `found_count`, `kept_count`, `search_calls` | Lancements, pages trouvées, offres retenues et appels à Tavily du mois |
| `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` | Jetons du mois |
| `deleted_at` | Date de la suppression du compte (UTC) |

Le coût n'est pas enregistré : l'API le calcule à chaque lecture, en dollars, à partir des jetons, des appels et des tarifs de `config.py` (`MODEL_PRICES_USD`, `TAVILY_CREDIT_PRICE_USD`, `TAVILY_CREDITS_PER_SEARCH`). Corriger un tarif corrige donc aussi le coût affiché des recherches passées. Un modèle sans tarif n'a pas de coût affiché. Les routes renvoient `search_cost_usd`, `model_cost_usd` et `cost_usd` pour un lancement, `model_cost_usd` pour une page.

### Faire évoluer le schéma

Les tables sont décrites dans `src/projet_recherche_emploi/data/models.py`. Modifier ce fichier ne change aucune base existante : il faut une migration, que l'application appliquera à son prochain démarrage, en local comme en ligne (l'image Docker l'applique avant de servir, et refuse de démarrer si elle échoue).

```bash
uv run projet-recherche-emploi migrate                    # la base locale doit d'abord être à jour
uv run alembic revision --autogenerate -m "ajout de la colonne note" --rev-id 0004
uv run pytest                                             # vérifie que modèles et migrations décrivent le même schéma
```

La deuxième commande compare les modèles à la base locale et écrit la migration dans `src/projet_recherche_emploi/data/migrations/versions/`. La relire avant de la committer : Alembic ne devine pas tout (un renommage de colonne, par exemple, est vu comme une suppression suivie d'un ajout).

Avant d'appliquer une migration à une base existante, l'application en fait une copie dans le même dossier, nommée `jobs.avant-migration-<version>.db`. Pour revenir en arrière, arrêter l'application et remettre cette copie à la place de `jobs.db`. Ces copies contiennent les données de tous les utilisateurs : les supprimer une fois la migration vérifiée. La suppression d'un compte retire ses données de chacune, sans les effacer.

## Configuration

Les postes recherchés et le CV se règlent dans l'application. Le reste se règle dans le code :

| Réglage | Fichier | Valeur par défaut |
|---|---|---|
| Dossier de la base et du CV (`DATA_DIR`) | variable d'environnement | dossier courant |
| Nom de la base (`DB_FILE_NAME`) | `src/projet_recherche_emploi/config.py` | `jobs.db` |
| Dossier du front Angular construit (`FRONTEND_DIR`) | variable d'environnement | `frontend/dist/frontend/browser` |
| Mot de passe de l'application (`APP_PASSWORD`) | variable d'environnement | aucun |
| Connexion Google (`GOOGLE_CLIENT_ID`, `OWNER_EMAIL`, `ALLOWED_EMAILS`…) | variables d'environnement | désactivée |
| Recherches par jour pour un invité (`MAX_SEARCHES_PER_DAY`) | `src/projet_recherche_emploi/config.py` | `2` |
| Jours sans activité avant la suppression d'un compte d'invité (`INACTIVE_ACCOUNT_DAYS`) | `src/projet_recherche_emploi/config.py` | `365` |
| Modèle OpenAI du filtre (`FILTER_MODEL`) | `src/projet_recherche_emploi/config.py` | `gpt-5-mini` |
| Taille maximale de page envoyée au modèle (`MAX_PAGE_CHARS`) | `src/projet_recherche_emploi/config.py` | `8000` |
| Recherches créées avec la base (`DEFAULT_QUERIES`) | `src/projet_recherche_emploi/config.py` | 2 recherches CDI, 2 freelance (ingénieur IA) |
| Types de contrat proposés (`CONTRACT_TYPES`) | `src/projet_recherche_emploi/config.py` | CDI, freelance, CDD, alternance, stage |
| Sites autorisés à appeler l'API depuis un navigateur (`CORS_ORIGINS`) | variable d'environnement | aucun |
| Sites interrogés (`JOB_SITES`) | `src/projet_recherche_emploi/config.py` | 24 sites d'emploi |
| Sites ajoutés pour la variante en anglais d'une recherche en télétravail complet (`REMOTE_JOB_SITES`) | `src/projet_recherche_emploi/config.py` | 7 sites d'offres en télétravail |
| Critères du filtre (`FILTER_PROMPT`) | `src/projet_recherche_emploi/agent/prompts.py` | — |

Les variables d'environnement sont lues une seule fois, au démarrage, dans la classe `Settings` de `config.py`.

Après une modification de `FILTER_PROMPT`, les pages déjà rejetées ne sont pas réévaluées. Pour les soumettre à nouveau, vider la table : `sqlite3 jobs.db "DELETE FROM rejected_jobs"`.

`DEFAULT_QUERIES` n'est utilisé qu'à la création de la base : une fois les recherches modifiées dans l'application, il n'a plus d'effet.

## Tests

```bash
uv run pytest          # tests
uv run ruff check .    # linter
```

Ceux du front se lancent à part, depuis `frontend/` (voir [Front Angular](#front-angular)) : ils simulent l'API, et couvrent chaque écran, la session et le suivi d'une recherche.

Les tests de bout en bout (`npm run e2e`, dans `frontend/e2e/`) déroulent un parcours complet dans Chrome, devant l'application entière : connexion, dépôt du CV, ajout d'un poste, recherche suivie en direct, candidature, suppression d'une offre, rejets, thème, déconnexion. [Playwright](https://playwright.dev/) lance pour cela `tests/e2e_server.py`, un serveur sur une base temporaire où Tavily et OpenAI sont remplacés par des faux : rien n'est facturé. Ils demandent `uv`, Chrome, et un front construit (`npm run build`).

Les tests tournent sur une base temporaire et n'appellent ni Tavily ni OpenAI. Ils vérifient notamment que :

- les données d'un utilisateur ne sont ni visibles ni modifiables par un autre, dans les dépôts, les services et l'API ;
- une base créée avant Alembic garde ses lignes après migration, et les modèles décrivent bien le schéma migré ;
- une recherche utilise les recherches et le CV de son utilisateur, et respecte le quota journalier ;
- toute route de l'API qui touche aux données exige une identité ;
- un cookie de session falsifié, expiré ou présenté par un autre site est refusé ;
- la documentation de l'API n'est pas servie en ligne, et une connexion à moitié réglée arrête le serveur ;
- le front est servi à la racine sans masquer l'API ni sortir de son dossier ;
- aucune couche n'importe une couche située au-dessus d'elle.

## Structure du projet

Le serveur est rangé en couches. Une interface (l'API, la commande) appelle les services, les services appellent les dépôts, et seuls les dépôts touchent à la base. Aucune couche n'importe celle du dessus, et les services ne connaissent pas FastAPI. Le front est une application à part, qui ne voit le serveur qu'à travers l'API.

```
src/projet_recherche_emploi/
├── config.py            # réglages : variables d'environnement (Settings) et constantes
├── errors.py            # erreurs destinées à l'utilisateur
├── schemas.py           # objets échangés entre services et interfaces (Pydantic)
├── container.py         # assemblage : relie réglages, base, graph et services
├── cli.py               # commande projet-recherche-emploi
├── api/                 # serveur FastAPI, seule couche qui importe fastapi
│   ├── main.py          # construction du serveur, traduction des erreurs en codes HTTP
│   ├── security.py      # identification de l'appelant (jeton Google ou mot de passe), cookie de session
│   ├── routers/         # routes : compte, offres, postes recherchés, CV, recherche
│   ├── public_pages.py  # pages HTML servies sans connexion (textes légaux, validation Google)
│   ├── frontend.py      # fichiers du front Angular, servis à la racine
│   └── legal/           # textes des règles de confidentialité et des conditions d'utilisation
├── services/            # règles métier, sans dépendance à une interface
│   ├── account_service.py # suppression d'un compte et de tout ce qu'il contient
│   ├── auth_service.py    # adresse Google -> utilisateur, mot de passe de l'instance, jeton de session
│   ├── search_service.py  # conditions préalables, quota journalier, lancement d'une recherche, bilans et synthèse
│   ├── search_costs.py    # coût d'une recherche, à partir de sa consommation et des tarifs
│   ├── usage_service.py   # consommation et coût de chaque compte, pour les administrateurs
│   ├── cv_service.py      # enregistrement du CV et de son texte sans coordonnées, oubli des rejets de l'ancien
│   ├── job_service.py     # offres retenues et pages rejetées
│   └── query_service.py   # postes recherchés
├── agent/               # recherche LangGraph
│   ├── graph.py         # construction du graph
│   ├── nodes.py         # les quatre étapes : search_jobs, filter_duplicates, filter_jobs, insert_jobs
│   ├── ports.py         # ce que le graph attend de l'extérieur : un moteur de recherche, un évaluateur
│   ├── adapters.py      # leurs branchements réels : Tavily et OpenAI
│   ├── prompts.py       # critères du filtre envoyés au modèle
│   └── state.py         # état partagé entre les étapes
└── data/                # seuls accès à la base et aux fichiers, seule couche qui importe sqlalchemy
    ├── database.py      # sessions, transactions, application des migrations
    ├── models.py        # tables (SQLAlchemy)
    ├── migrations/      # migrations Alembic
    ├── repositories/    # un dépôt par table
    │   ├── job_repository.py           # offres : insertion, lecture, suivi des candidatures, suppression
    │   ├── rejected_job_repository.py  # pages rejetées : insertion, lecture, vidage
    │   ├── query_repository.py         # postes recherchés : lecture, ajout, suppression
    │   ├── search_run_repository.py    # lancements de recherche : quota journalier, bilan
    │   ├── page_evaluation_repository.py  # journal des pages évaluées
    │   ├── usage_repository.py         # consommation additionnée par compte, pour les administrateurs
    │   ├── user_repository.py          # comptes
    │   └── cv_text_repository.py       # texte des CV, coordonnées retirées, et date du dépôt
    └── cv_ingestion/    # du PDF déposé au texte enregistré : le PDF n'est pas conservé
        ├── ingestion.py     # lit le PDF, retire les coordonnées, enregistre le texte
        ├── pdf_reader.py    # texte d'un PDF, refus d'un fichier illisible ou sans texte
        └── anonymizer.py    # retire d'un CV les coordonnées et le nom

frontend/src/
├── environments/        # adresse de l'API, clé de licence PrimeNG reçue au build
├── styles.scss          # identité visuelle : couleurs, typographie, thème sombre
└── app/
    ├── core/            # appels à l'API, session, gardes de route, thème, suivi d'une recherche
    ├── login/           # écran de connexion
    ├── shell/           # cadre de l'application : en-tête, navigation, bouton de lancement
    ├── run/             # suivi en direct d'une recherche
    ├── jobs/            # rubrique Offres
    ├── rejected/        # rubrique Rejets
    └── profile/         # rubrique Profil : CV et postes recherchés
```
