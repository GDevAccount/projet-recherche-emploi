from langchain_core.prompts import ChatPromptTemplate

FILTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Tu évalues des pages web trouvées lors d'une recherche d'emploi, pour un candidat dont voici le CV.\n\n"
            "CV :\n{cv}\n\n"
            "Pour la page fournie, détermine :\n"
            "- is_real_offer : vrai seulement si la page décrit UNE offre d'emploi ou mission précise "
            "(un poste, une entreprise ou un client, des missions). Faux pour une liste ou une page de "
            "résultats de recherche regroupant plusieurs offres, un article, une fiche métier, une "
            "formation, une page d'accueil, une offre expirée ou une offre qui ne se situe pas en région parisienne.\n"
            "- matches_cv : vrai seulement si le poste correspond au profil du candidat "
            "(compétences, niveau d'expérience, domaine).\n"
            "- reason : une phrase qui justifie la décision.",
        ),
        ("human", "Titre : {title}\nURL : {url}\n\nContenu de la page :\n{page}"),
    ]
)
