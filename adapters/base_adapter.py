"""
Abstract Base Adapter for Job Application Portals.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import Page
from core.stealth import StealthDriver
from core.storage import ApplicationStore
from engine.deterministic_resolver import DeterministicResolver
from engine.llm_router import LLMRouter


class BaseAdapter(ABC):
    def __init__(
        self,
        resolver: DeterministicResolver,
        llm_router: LLMRouter,
        stealth: StealthDriver,
        storage: ApplicationStore,
        settings: Dict[str, Any]
    ):
        self.resolver = resolver
        self.llm_router = llm_router
        self.stealth = stealth
        self.storage = storage
        self.settings = settings
        self.resume_path = settings.get("resume", {}).get("path", "resumes/resume.pdf")

    @abstractmethod
    async def can_handle(self, page: Page) -> bool:
        """Determines if this adapter can handle the current page/modal."""
        pass

    @abstractmethod
    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        """
        Fills the application.
        In 'copilot' mode: autofills and pauses right before submit.
        In 'autonomous' mode: auto-submits and logs.
        """
        pass
