"""Flux d'événements (Server-Sent Events) : ce que partagent les routes qui répondent au fur et à mesure."""

import queue
import threading
from collections.abc import Iterator
from typing import TypeVar

Event = TypeVar("Event")


def run_detached(events: Iterator[Event]) -> Iterator[Event | Exception]:
    """Déroule ces événements dans un fil à part, et les rend à mesure ; une erreur est rendue, pas levée.

    Si le navigateur ferme la connexion, le travail va quand même au bout : ce qui a été payé chez Tavily ou
    OpenAI est enregistré, et compté.
    """
    done = object()
    results: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            for event in events:
                results.put(event)
        except Exception as error:
            results.put(error)
        finally:
            results.put(done)

    threading.Thread(target=work, daemon=True).start()
    while (item := results.get()) is not done:
        yield item


def server_sent_event(name: str, data: str) -> str:
    return f"event: {name}\ndata: {data}\n\n"
