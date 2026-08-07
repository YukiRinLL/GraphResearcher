"""Optional Langfuse observability boundary for research runs."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_REQUIRED_ENVIRONMENT_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
_RUN_NAME = "graphresearcher.research"


@dataclass(frozen=True)
class LangfuseRun:
    """Hold the optional callback and client for one research run."""

    callback: Any | None = None
    client: Any | None = None
    session_id: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        """Return whether this run is sending events to Langfuse."""
        return self.callback is not None

    def langchain_config(self) -> dict[str, Any]:
        """Return the callback configuration accepted by LangChain runnables."""
        if not self.enabled:
            return {}
        return {
            "callbacks": [self.callback],
            "run_name": _RUN_NAME,
            "metadata": {
                "langfuse_session_id": self.session_id,
                "langfuse_tags": ["graphresearcher"],
                **(self.metadata or {}),
            },
        }

    def flush(self) -> None:
        """Flush queued Langfuse events without interrupting report delivery."""
        if self.client is None:
            return
        try:
            self.client.flush()
        except Exception as exc:  # noqa: BLE001 - observability must be best-effort
            logger.warning("Langfuse flush failed: %s", exc)


def start_langfuse_run(
    output_dir: Path,
    max_search_rounds: int,
    model_name: str,
    environ: Mapping[str, str] | None = None,
) -> LangfuseRun:
    """Build an optional Langfuse callback for one top-level research run.

    Langfuse is enabled only when both required credentials are present. Import
    and SDK setup failures are deliberately non-fatal so observability never
    changes the research run's delivery behavior.

    Args:
        output_dir: Directory receiving this run's local artifacts.
        max_search_rounds: Configured upper bound for Searcher dispatches.
        model_name: Model identifier included in Langfuse metadata.
        environ: Optional environment mapping, mainly for deterministic tests.

    Returns:
        A disabled run when Langfuse is unconfigured or unavailable; otherwise
        a run with a LangChain callback and flushable Langfuse client.
    """
    environment = os.environ if environ is None else environ
    if not all(environment.get(key) for key in _REQUIRED_ENVIRONMENT_KEYS):
        return LangfuseRun()

    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        client = get_client()
        callback = CallbackHandler()
    except Exception as exc:  # noqa: BLE001 - optional SDK setup
        logger.warning("Langfuse is configured but could not be initialized: %s", exc)
        return LangfuseRun()

    return LangfuseRun(
        callback=callback,
        client=client,
        session_id=uuid.uuid4().hex,
        metadata={
            "graphresearcher_model": model_name,
            "graphresearcher_max_search_rounds": max_search_rounds,
            "graphresearcher_output_dir": output_dir.name,
        },
    )
