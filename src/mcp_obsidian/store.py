"""Persistencia en disco de los tokens OAuth.

En memoria, cada reinicio del servidor invalida la sesión del cliente en silencio: responde
401 y conectores como el de Gemini no rehacen el flujo por su cuenta, simplemente dejan de
funcionar. Los códigos de autorización no se guardan: duran cinco minutos y son de un solo
uso, así que no compensa escribirlos a disco.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SECTIONS = ("access", "refresh")


class TokenStore:
    """Tokens respaldados por un JSON que solo puede leer su dueño."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, dict[str, Any]]] = {section: {} for section in SECTIONS}
        self._load()

    def _load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("No se pudo leer %s (%s). Se arranca sin tokens.", self._path, exc)
            return

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("%s no es JSON válido. Se descarta y se arranca sin tokens.", self._path)
            return

        if not isinstance(parsed, dict):
            return
        for section in SECTIONS:
            entries = parsed.get(section)
            if isinstance(entries, dict):
                self._data[section] = entries
        self.prune()

    def _save(self) -> None:
        tmp = self._path.with_name(f".{self._path.name}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Se crea ya con 0600: el token nunca llega a existir siendo legible por terceros.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle)
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.warning("No se pudieron guardar los tokens en %s (%s).", self._path, exc)
            tmp.unlink(missing_ok=True)

    def prune(self) -> None:
        now = time.time()
        removed = False
        for entries in self._data.values():
            for key, value in list(entries.items()):
                expires_at = value.get("expires_at")
                if expires_at is not None and expires_at < now:
                    del entries[key]
                    removed = True
        if removed:
            self._save()

    def get(self, section: str, key: str) -> dict[str, Any] | None:
        return self._data[section].get(key)

    def put(self, section: str, key: str, value: dict[str, Any]) -> None:
        self._data[section][key] = value
        self._save()

    def pop(self, section: str, key: str) -> None:
        if self._data[section].pop(key, None) is not None:
            self._save()
