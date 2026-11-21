"""
Automatic Resume Sync & Profile Extractor.
Monitors resumes/resume.pdf for changes. Whenever you update your resume PDF,
this module extracts updated skills, projects, and contact details automatically
using Gemini multimodal PDF understanding, updating config/profile.yaml with zero manual effort.
"""

import hashlib
import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ResumeSync:
    def __init__(self, base_dir: Path, settings: Dict[str, Any]):
        self.base_dir = base_dir
        self.settings = settings
        self.resume_path = base_dir / settings.get("resume", {}).get("path", "resumes/resume.pdf")
        self.hash_file = base_dir / "data" / "resume_hash.txt"
        self.profile_path = base_dir / "config" / "profile.yaml"

        ai_config = settings.get("ai", {})
        self.gemini_key = os.getenv(ai_config.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY"), "")
        self.gemini_model = ai_config.get("gemini", {}).get("model", "gemini-2.0-flash")

    def _compute_hash(self) -> str:
        if not self.resume_path.exists():
            return ""
        hasher = hashlib.md5()
        with open(self.resume_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_resume_updated(self) -> bool:
        if not self.resume_path.exists():
            return False
        current_hash = self._compute_hash()
        if not self.hash_file.exists():
            return True
        with open(self.hash_file, "r") as f:
            stored_hash = f.read().strip()
        return current_hash != stored_hash

    def mark_synced(self):
        current_hash = self._compute_hash()
        self.hash_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.hash_file, "w") as f:
            f.write(current_hash)

    def auto_sync_if_needed(self) -> bool:
        """Checks if resume changed and automatically refreshes profile.yaml."""
        if not self.is_resume_updated():
            return False

        print(f"\n📄 Detected updated resume at: {self.resume_path}")
        print("🤖 Auto-syncing candidate profile from PDF (zero manual config needed)...")

        extracted = self._extract_from_pdf()
        if not extracted:
            print("⚠️ Could not auto-extract from PDF (using existing profile.yaml).")
            return False

        # Merge with existing profile to preserve custom manual overrides if any
        existing_profile = {}
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    existing_profile = yaml.safe_load(f) or {}
            except Exception:
                existing_profile = {}

        merged = self._merge_profiles(existing_profile, extracted)

        # Write updated profile.yaml
        with open(self.profile_path, "w", encoding="utf-8") as f:
            yaml.dump(merged, f, sort_keys=False, allow_unicode=True)

        self.mark_synced()
        print("✅ Successfully updated config/profile.yaml from your latest resume!\n")
        return True

    def _extract_from_pdf(self) -> Optional[Dict[str, Any]]:
        if not self.gemini_key:
            print("ℹ️ Set GEMINI_API_KEY to enable AI-powered multimodal PDF resume parsing.")
            return None

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.gemini_key)
            with open(self.resume_path, "rb") as f:
                pdf_bytes = f.read()

            prompt = """
            Analyze this candidate resume PDF and output a valid YAML or JSON object with the following exact structure:
            
            personal:
              first_name: "..."
              last_name: "..."
              full_name: "..."
              email: "..."
              phone: "..."
              city: "..."
              state: "..."
              country: "..."
            socials:
              linkedin: "..."
              github: "..."
              portfolio: "..."
            skills_and_experience:
              total_years_experience: 3.0
              skill_years:
                Skill1: 3
                Skill2: 2
            education:
              degree: "..."
              field_of_study: "..."
              institution: "..."
              graduation_year: 2023
            heuristics:
              summary: "A crisp 2-sentence professional summary of this candidate."
              proudest_project: "The top achievement or project mentioned on the resume."
              
            Output ONLY valid YAML. No commentary, no markdown codeblocks.
            """

            response = client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt
                ]
            )

            text = response.text.strip()
            # Clean possible markdown block formatting
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n", "", text)
                text = re.sub(r"\n```$", "", text)

            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else None

        except Exception as e:
            print(f"⚠️ PDF extraction error: {e}")
            return None

    def _merge_profiles(self, existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge extracted fields while preserving user preference overrides like salary/notice."""
        merged = dict(existing)
        for key, val in extracted.items():
            if isinstance(val, dict) and key in merged and isinstance(merged[key], dict):
                merged[key].update(val)
            else:
                merged[key] = val
        return merged
