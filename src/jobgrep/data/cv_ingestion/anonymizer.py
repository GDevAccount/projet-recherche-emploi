"""Retire d'un CV ce qui identifie la personne ou permet de la joindre.

Le texte du CV est envoyé à OpenAI avec chaque page à évaluer. Le modèle juge des compétences et un niveau :
il n'a besoin ni du nom, ni du téléphone, ni de l'adresse. Ces champs sont remplacés par une étiquette avant
que le texte soit enregistré, et c'est ce texte-là que le filtre lit.

La reconnaissance se fait par motifs : elle retire ce qui a la forme d'une coordonnée, sans garantie de tout
trouver. Dans le doute, un motif laisse le texte en place plutôt que d'effacer une compétence.
"""

import re
from collections.abc import Iterable

EMAIL_LABEL = "[e-mail]"
PHONE_LABEL = "[téléphone]"
LINK_LABEL = "[lien]"
ADDRESS_LABEL = "[adresse]"
BIRTH_LABEL = "[date de naissance]"
NAME_LABEL = "[nom]"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Sites de profil, reconnus même sans « https:// » ni chemin
PROFILE_SITES = "linkedin|github|gitlab|bitbucket|malt|medium|behance|dribbble|stackoverflow|twitter"
# Un nom de domaine nu n'est un lien que s'il est suivi d'un chemin, et seulement pour ces extensions :
# « Node.js », « ASP.NET » ou « Socket.io » sont des compétences, pas des adresses
SITE_SUFFIXES = "com|fr|io|dev|net|org|me|eu|app|ai|co|be|ch|ca|uk|de|tech|page"
LINK = re.compile(
    rf"(?:https?://|www\.)\S+"
    rf"|\b(?:{PROFILE_SITES})\.(?:com|fr|io)(?:/\S*)?"
    rf"|\b(?:[\w-]+\.)+(?:{SITE_SUFFIXES})/\S+",
    re.IGNORECASE,
)

# Numéro international (+33 6 12 34 56 78, 0033…), ou français à dix chiffres (06 12 34 56 78, 06.12.34.56.78).
# Une période « 2019 - 2023 » ne commence ni par « + » ni par « 0 » : elle reste.
PHONE = re.compile(
    r"(?<![\w+])"
    r"(?:(?:\+|00)[1-9]\d{0,2}(?:[\s.\-()]*\d){8,12}"
    r"|0[1-9](?:[\s.\-]?\d{2}){4})"
    r"(?!\d)"
)

STREET_WORDS = "rue|avenue|av|boulevard|bd|chemin|impasse|allée|allee|place|quai|route|cours|square|passage|villa"
# Numéro et voie : « 12 bis rue des Lilas », « 12b rue des Lilas ». La ville et le code postal restent,
# ils ne désignent personne
STREET = re.compile(rf"\b\d{{1,4}}\s?(?:bis|ter|[a-z])?,?\s+(?:{STREET_WORDS})\b\.?[^\n,;|]*", re.IGNORECASE)

BIRTH = re.compile(r"\b(?:n[ée]e?\s+le|date\s+de\s+naissance)\s*:?\s*[^\n,;|]*", re.IGNORECASE)

# Un mot aussi court est une particule (« de », « le ») ou une initiale : le retirer partout abîmerait le texte
MIN_NAME_LENGTH = 3


class CvAnonymizer:
    """Remplace les coordonnées d'un CV par des étiquettes : e-mail, téléphone, liens, adresse, naissance, nom."""

    def anonymize(self, text: str, names: Iterable[str] = ()) -> str:
        """Renvoie le texte sans ses coordonnées.

        « names » donne les noms connus de la personne (celui de son compte Google) : un nom ne se reconnaît
        pas à sa forme, il n'est donc retiré que s'il est fourni.
        """
        # Les e-mails et les liens d'abord : ils contiennent souvent le nom, et parfois des chiffres
        for pattern, label in (
            (EMAIL, EMAIL_LABEL),
            (LINK, LINK_LABEL),
            (PHONE, PHONE_LABEL),
            (STREET, ADDRESS_LABEL),
            (BIRTH, BIRTH_LABEL),
        ):
            text = pattern.sub(label, text)
        for word in self._name_words(names):
            text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", NAME_LABEL, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _name_words(names: Iterable[str]) -> list[str]:
        words = {word for name in names for word in re.findall(r"[^\W\d_]+", name) if len(word) >= MIN_NAME_LENGTH}
        # Les plus longs d'abord : « Martine » ne doit pas devenir « [nom]e » à cause de « Martin »
        return sorted(words, key=len, reverse=True)
