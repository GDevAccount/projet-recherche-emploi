import pytest

from projet_recherche_emploi.services.cv_anonymizer import CvAnonymizer


@pytest.fixture
def anonymizer():
    return CvAnonymizer()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Contact : alice.martin+emploi@exemple.fr", "Contact : [e-mail]"),
        ("06 12 34 56 78", "[téléphone]"),
        ("Tél. 06.12.34.56.78 (mobile)", "Tél. [téléphone] (mobile)"),
        ("0612345678", "[téléphone]"),
        ("+33 6 12 34 56 78", "[téléphone]"),
        ("+33 (0)6 12 34 56 78", "[téléphone]"),
        ("0033612345678", "[téléphone]"),
        ("+1 415-555-0132", "[téléphone]"),
        ("https://www.linkedin.com/in/alice-martin-0123", "[lien]"),
        ("linkedin.com/in/alice-martin", "[lien]"),
        ("Code : github.com/alicemartin", "Code : [lien]"),
        ("www.alice-martin.fr", "[lien]"),
        ("Portfolio : alice-martin.dev/projets", "Portfolio : [lien]"),
        ("12 rue des Lilas\n75011 Paris", "[adresse]\n75011 Paris"),
        ("12b rue du 11 Novembre 1918", "[adresse]"),
        ("3 bis, avenue Jean Jaurès, Lyon", "[adresse], Lyon"),
        ("Née le 12/03/1990 à Rennes", "[date de naissance]"),
        ("Date de naissance : 12 mars 1990 | Permis B", "[date de naissance]| Permis B"),
    ],
)
def test_contact_details_are_replaced_by_a_label(anonymizer, text, expected):
    assert anonymizer.anonymize(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # Périodes, durées et versions : des chiffres qui ne sont pas un téléphone
        "2019 - 2023 : Ingénieur IA chez Exemple",
        "01/2021 - 06/2023",
        "10 ans d'expérience, dont 4 en management",
        "Python 3.11, PostgreSQL 16, 1 000 000 de requêtes par jour",
        # Technologies dont le nom ressemble à une adresse de site
        "Node.js, Vue.js, ASP.NET, Socket.io, Next.js/React, CI/CD, TCP/IP",
        # Un poste « chez » une entreprise, écrit avec une arobase
        "Lead Data Engineer @ Exemple",
        # La ville reste : elle ne désigne personne
        "75011 Paris",
        "Projet de rue connectée pour la ville de Lyon",
    ],
)
def test_what_serves_the_evaluation_is_kept(anonymizer, text):
    assert anonymizer.anonymize(text) == text


def test_known_names_are_removed_whatever_their_case(anonymizer):
    text = "ALICE MARTIN\nIngénieure IA\nalice martin a encadré l'équipe de Martine Durand."

    anonymized = anonymizer.anonymize(text, ["Alice Martin"])

    assert anonymized == "[nom] [nom]\nIngénieure IA\n[nom] [nom] a encadré l'équipe de Martine Durand."


def test_name_inside_an_address_or_a_link_leaves_no_trace(anonymizer):
    text = "Alice Martin - alice.martin@exemple.fr - linkedin.com/in/alice-martin"

    assert anonymizer.anonymize(text, ["Alice Martin"]) == "[nom] [nom] - [e-mail] - [lien]"


def test_particles_and_initials_of_a_name_are_not_removed_everywhere(anonymizer):
    text = "Jean de La Fontaine, auteur de fables et de contes"

    # « de » et « La » sont trop courts pour être retirés partout sans abîmer le texte
    assert anonymizer.anonymize(text, ["Jean de La Fontaine"]) == "[nom] de La [nom], auteur de fables et de contes"


def test_without_a_known_name_the_name_stays(anonymizer):
    # Un nom ne se reconnaît pas à sa forme : il n'est retiré que s'il est fourni
    assert anonymizer.anonymize("Alice Martin\nIngénieure IA") == "Alice Martin\nIngénieure IA"
