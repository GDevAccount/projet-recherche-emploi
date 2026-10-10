import hashlib
from collections.abc import Iterable

from langchain_core.prompts import ChatPromptTemplate

AREA_RULE = (
    "vrai si le lieu du poste (work_city, work_country) se trouve dans l'une de ces zones géographiques, "
    "acceptées par le candidat : {accepted_areas}. Une ville située dans une région ou un département "
    "acceptés convient. Ne juger que la géographie, sans tenir compte du télétravail. "
    "Vrai si la page ne dit pas où se trouve le poste."
)
# Toutes les recherches sont en télétravail complet : il n'y a pas de géographie à juger
NO_AREA_RULE = "toujours faux : le candidat n'accepte aucune zone géographique."


def describe_area_rule(accepted_areas: str) -> str:
    """Renvoie la consigne du champ in_accepted_area : seule la règle qui s'applique est écrite dans le prompt."""
    return AREA_RULE.format(accepted_areas=accepted_areas) if accepted_areas else NO_AREA_RULE


def describe_sought_jobs(sought_jobs: Iterable[str]) -> str:
    """Renvoie les phrases de recherche du candidat, une par ligne."""
    return "\n".join(f"- {job}" for job in sought_jobs)


FILTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Tu évalues des pages web trouvées lors d'une recherche d'emploi, pour un candidat dont voici le CV.\n\n"
            "CV :\n{cv}\n\n"
            "Postes que le candidat recherche (les phrases qu'il a saisies dans un moteur de recherche) :\n"
            "{sought_jobs}\n\n"
            "Pour la page fournie, détermine :\n"
            "- page_kind : la nature de la page. « offre » seulement si elle décrit UNE offre d'emploi ou "
            "mission précise, encore ouverte (un poste, une entreprise ou un client, des missions). Sinon : "
            "« liste d'offres » pour une liste ou une page de résultats de recherche regroupant plusieurs "
            "offres ; « offre expirée » pour une offre précise qui n'est plus ouverte (pourvue, retirée, "
            "candidatures closes) ; « formation » pour une formation, une école ou un cours, et non un "
            "poste ; « fiche métier » pour la description générale d'un métier ou de ses salaires ; "
            "« article » pour un article, un billet de blog ou une actualité ; « page d'accueil » pour "
            "l'accueil d'un site ou la présentation d'une entreprise ; « autre » pour tout le reste "
            "(page d'erreur, page de connexion, profil d'une personne).\n"
            "- contract_type : le type de contrat écrit sur la page (CDI, freelance, CDD, alternance ou stage). "
            "Une mission pour indépendant ou en portage salarial est un freelance. "
            "null si la page ne le dit pas ou n'est pas une offre : ne pas le deviner.\n"
            "- work_city : la ville du poste ou du siège de l'employeur, telle que la page l'écrit "
            "(par exemple « Lyon »). null si la page ne la donne pas.\n"
            "- work_country : le pays de cette ville, en français (par exemple « France », « États-Unis »). "
            "null si la page ne permet pas de le savoir.\n"
            "- work_mode : « télétravail complet » si la page écrit que le poste est à 100 % à distance "
            "(full remote), « hybride » s'il mêle bureau et télétravail, « sur site » s'il se tient au "
            "bureau. null si la page ne le dit pas : ne pas le deviner.\n"
            "- in_accepted_area : {area_rule}\n"
            "- open_to_candidates_in_france : faux seulement si la page réserve le poste aux personnes qui "
            "résident ou sont autorisées à travailler dans un pays ou une zone qui n'inclut pas la France "
            "(« US residents only », « must be based in Canada », « LATAM »). Vrai si la zone inclut la "
            "France (« Europe », « EMEA », « worldwide ») ou si la page ne pose aucune condition de ce type.\n"
            "- matches_search : vrai seulement si le métier du poste est l'un de ceux que le candidat "
            "recherche, sous cet intitulé ou un intitulé équivalent (pour « ingénieur IA » : AI engineer, "
            "ingénieur LLM, ingénieur GenAI). Ne retenir des phrases de recherche que le métier : le lieu et "
            "le contrat qu'elles citent sont jugés ailleurs. Le CV ne compte pas ici : un métier que le "
            "candidat a déjà exercé mais qu'il ne recherche pas est faux (un poste de développeur full stack "
            "pour qui recherche un poste d'ingénieur IA). Dans le doute, faux : le candidat préfère manquer "
            "une offre que trier des offres hors sujet.\n"
            "- matches_skills : vrai si le CV couvre les compétences principales du poste, directement ou par "
            "une technologie voisine qui s'apprend vite (LlamaIndex pour qui connaît LangChain, AWS pour qui "
            "connaît GCP). Les compétences « souhaitées » ou « un plus » ne comptent pas. Faux si le cœur du "
            "poste repose sur un domaine absent du CV.\n"
            "- matches_level : vrai si l'expérience du candidat est compatible avec le poste. Quelques années "
            "de moins que demandé conviennent : une annonce décrit un candidat idéal. Un poste en dessous de "
            "son niveau convient aussi. Un poste de lead ou de management convient si le parcours du CV le "
            "rend crédible (dix ans de développement pour un poste de lead developer). Faux seulement si "
            "l'écart est manifeste. Ne pas tenir compte du type de contrat.\n"
            "- reason : une ou deux phrases courtes en français, écrites pour le candidat : ce qui fait que "
            "l'offre lui convient, ou ce qui l'écarte (pas une offre, autre métier, compétences, niveau). "
            "Ne pas réciter les faits lus sur la page ni les noms des champs ci-dessus.\n\n"
            "Si page_kind n'est pas « offre », mettre faux à matches_search, matches_skills et matches_level.",
        ),
        ("human", "Titre : {title}\nURL : {url}\n\nContenu de la page :\n{page}"),
    ]
)


def prompt_version() -> str:
    """Renvoie l'empreinte du prompt du filtre : elle change dès qu'un mot de ses consignes change.

    Enregistrée avec chaque lancement, elle dit quelles recherches ont été jugées avec les mêmes consignes.
    """
    templates = [message.prompt.template for message in FILTER_PROMPT.messages]
    text = "\n".join([*templates, AREA_RULE, NO_AREA_RULE])
    return hashlib.sha256(text.encode()).hexdigest()[:12]
