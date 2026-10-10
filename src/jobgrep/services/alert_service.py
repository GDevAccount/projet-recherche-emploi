"""Alertes envoyées à qui exploite l'instance : une recherche échouée, une panne, un coût anormal.

Un message ne porte que le type d'un incident et des nombres : jamais une adresse, un titre, un lien ni un
message d'erreur. Il part chez un tiers (ntfy), sur un sujet que quiconque en connaît le nom peut lire.
"""

import json
import logging
import threading
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from jobgrep.config import ALERT_QUIET_MINUTES

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 5
# Priorité « haute » de ntfy : le téléphone sonne même en mode discret léger
NTFY_PRIORITY = 4
NTFY_TAGS = ["warning"]
TEST_TITLE = "Alerte d'essai"
TEST_MESSAGE = "Les alertes de JobGrep arrivent bien ici."


class Notifier(Protocol):
    def send(self, title: str, message: str) -> bool:
        """Envoie une alerte, et dit si elle est partie. Ne lève jamais."""
        ...


class NtfyNotifier:
    """Publie sur un sujet ntfy (https://ntfy.sh, ou un serveur à soi)."""

    def __init__(self, url: str, topic: str):
        self.url = url
        self.topic = topic

    def send(self, title: str, message: str) -> bool:
        body = {"topic": self.topic, "title": title, "message": message, "priority": NTFY_PRIORITY, "tags": NTFY_TAGS}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS) as response:
                return 200 <= response.status < 300
        except Exception as error:
            # Le type seul : le message de l'erreur porte l'adresse appelée, donc le nom du sujet
            logger.warning("L'alerte n'a pas pu être envoyée (%s)", type(error).__name__)
            return False


def send_in_background(send: Callable[[], object]) -> None:
    """Lance l'envoi sans faire attendre l'appelant : une alerte ne doit ralentir ni une réponse ni une recherche."""
    threading.Thread(target=send, daemon=True).start()


class AlertService:
    """Envoie les alertes, sans répéter la même avant un délai. Sans destinataire réglé, il ne fait rien."""

    def __init__(
        self, notifier: Notifier | None = None, dispatch: Callable[[Callable[[], object]], None] = send_in_background
    ):
        self.notifier = notifier
        # Façon de lancer un envoi : les tests y mettent un appel direct
        self.dispatch = dispatch
        # Dernier envoi de chaque alerte. En mémoire : un redémarrage remet les délais à zéro
        self._last_sent: dict[str, datetime] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.notifier is not None

    def notify(
        self,
        key: str,
        title: str,
        message: str,
        quiet: timedelta = timedelta(minutes=ALERT_QUIET_MINUTES),
        now: datetime | None = None,
    ) -> bool:
        """Envoie cette alerte, sauf si une alerte de même clé est partie depuis moins longtemps que le délai.

        Renvoie vrai si elle a été confiée à l'envoi. Ne lève jamais et n'attend pas la réponse du destinataire.
        """
        notifier = self.notifier
        if notifier is None:
            return False
        now = now or datetime.now(UTC)
        with self._lock:
            last = self._last_sent.get(key)
            if last is not None and now - last < quiet:
                return False
            self._last_sent[key] = now
        try:
            self.dispatch(lambda: notifier.send(title, message))
        except Exception:
            logger.exception("L'alerte « %s » n'a pas pu être lancée", title)
            return False
        return True

    def send_test(self) -> bool:
        """Envoie une alerte d'essai en attendant la réponse, et dit si elle est partie."""
        return self.notifier is not None and self.notifier.send(TEST_TITLE, TEST_MESSAGE)
