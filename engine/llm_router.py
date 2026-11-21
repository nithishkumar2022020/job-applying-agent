"""
High-Availability Zero-Cost AI Router.
Dual-provider failover: Primary (Google Gemini 2.0 Flash) -> Secondary (Groq Llama 3.3 70B)
Includes local semantic SQLite caching to eliminate redundant token consumption.
"""

import os
import re
from typing import Optional, Dict, Any
from core.storage import ApplicationStore


class LLMRouter:
    def __init__(self, settings: Dict[str, Any], profile: Dict[str, Any], storage: ApplicationStore):
        self.settings = settings
        self.profile = profile
        self.storage = storage

        ai_config = settings.get("ai", {})
        self.primary_provider = ai_config.get("primary_provider", "gemini")
        self.secondary_provider = ai_config.get("secondary_provider", "groq")
        self.enable_cache = ai_config.get("enable_cache", True)

        self.gemini_model = ai_config.get("gemini", {}).get("model", "gemini-2.0-flash")
        self.gemini_key = os.getenv(ai_config.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY"), "")

        self.groq_model = ai_config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
        self.groq_key = os.getenv(ai_config.get("groq", {}).get("api_key_env", "GROQ_API_KEY"), "")

        self._gemini_client = None
        self._groq_client = None

    def _get_gemini_client(self):
        if self._gemini_client is None:
            if not self.gemini_key:
                return None
            try:
                # Support new google-genai SDK or google-generativeai
                from google import genai
                self._gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception:
                try:
                    import google.generativeai as legacy_genai
                    legacy_genai.configure(api_key=self.gemini_key)
                    self._gemini_client = legacy_genai.GenerativeModel(self.gemini_model)
                except Exception:
                    self._gemini_client = None
        return self._gemini_client

    def _get_groq_client(self):
        if self._groq_client is None:
            if not self.groq_key:
                return None
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self.groq_key)
            except Exception:
                self._groq_client = None
        return self._groq_client

    def _build_system_prompt(self, job_title: str, company: str, job_description: str = "") -> str:
        summary = self.profile.get("heuristics", {}).get("summary", "")
        skills = ", ".join(self.profile.get("skills_and_experience", {}).get("skill_years", {}).keys())
        years = self.profile.get("skills_and_experience", {}).get("total_years_experience", 3)

        return (
            f"You are an assistant answering job application screening questions on behalf of a candidate.\n"
            f"Candidate: {self.profile.get('personal', {}).get('full_name')}\n"
            f"Experience: {years} years. Core skills: {skills}\n"
            f"Summary: {summary}\n"
            f"Target Role: {job_title} at {company}\n"
            f"Instructions:\n"
            f"1. Answer concisely, professionally, and directly in 1st person ('I').\n"
            f"2. For numerical questions (e.g., 'How many years of X?'), reply with JUST the number.\n"
            f"3. For yes/no questions, answer with 'Yes' or 'No'.\n"
            f"4. For short open-ended questions ('Why this role?'), reply in 2-3 crisp sentences maximum.\n"
            f"5. Do NOT include greetings, preamble, quotes, or markdown bolding."
        )

    async def answer_question(
        self,
        question: str,
        job_title: str = "Software Engineer",
        company: str = "Company",
        job_description: str = "",
        input_type: str = "text"
    ) -> str:
        """
        Answers a subjective ATS question using the high-availability failover pipeline.
        """
        # 1. Check local semantic cache
        if self.enable_cache:
            cached = self.storage.get_cached_answer(question)
            if cached:
                return cached["answer"]

        # 2. Try Primary Provider (Gemini)
        answer = None
        used_provider = None

        if self.primary_provider == "gemini":
            answer = self._call_gemini(question, job_title, company, job_description)
            if answer:
                used_provider = "gemini"

        # 3. Failover to Secondary Provider (Groq) if primary failed or not configured
        if not answer:
            answer = self._call_groq(question, job_title, company, job_description)
            if answer:
                used_provider = "groq"

        # 4. If secondary was primary or fallback needed
        if not answer and self.primary_provider != "gemini":
            answer = self._call_gemini(question, job_title, company, job_description)
            if answer:
                used_provider = "gemini"

        # 5. Last-resort heuristic fallback
        if not answer:
            answer = self._heuristic_fallback(question, input_type)
            used_provider = "heuristic_fallback"

        # Clean up answer
        clean_ans = self._clean_llm_output(answer, input_type)

        # 6. Save in SQLite cache
        if self.enable_cache and clean_ans:
            self.storage.save_cached_answer(question, clean_ans, used_provider)

        return clean_ans

    def _call_gemini(self, question: str, job_title: str, company: str, job_desc: str) -> Optional[str]:
        client = self._get_gemini_client()
        if not client:
            return None
        try:
            system_prompt = self._build_system_prompt(job_title, company, job_desc)
            prompt = f"{system_prompt}\n\nQuestion: {question}\nAnswer:"

            # Handle google.genai Client
            if hasattr(client, "models"):
                response = client.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt
                )
                return response.text.strip()
            # Handle google.generativeai GenerativeModel
            elif hasattr(client, "generate_content"):
                response = client.generate_content(prompt)
                return response.text.strip()
        except Exception as e:
            # Silently catch and trigger failover
            print(f"[AI Router] Gemini call failed ({e}). Failing over to Groq...")
            return None
        return None

    def _call_groq(self, question: str, job_title: str, company: str, job_desc: str) -> Optional[str]:
        client = self._get_groq_client()
        if not client:
            return None
        try:
            system_prompt = self._build_system_prompt(job_title, company, job_desc)
            completion = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Question: {question}\nAnswer:"}
                ],
                temperature=0.2,
                max_tokens=200,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AI Router] Groq call failed ({e}).")
            return None

    def _heuristic_fallback(self, question: str, input_type: str) -> str:
        q_lower = question.lower()
        if input_type == "number":
            return "3"
        if "why" in q_lower or "interest" in q_lower:
            return self.profile.get("heuristics", {}).get(
                "why_join", 
                "My experience in building scalable, production-grade applications directly aligns with this role."
            )
        if "project" in q_lower or "accomplish" in q_lower:
            return self.profile.get("heuristics", {}).get(
                "proudest_project",
                "I engineered a low-latency client architecture with offline sync and automated test coverage."
            )
        return self.profile.get("heuristics", {}).get("summary", "Experienced software engineer specializing in scalable application development.")

    @staticmethod
    def _clean_llm_output(output: str, input_type: str) -> str:
        text = output.strip().strip('"').strip("'")
        if text.lower().startswith("answer:"):
            text = text[7:].strip()
        if input_type == "number":
            numbers = re.findall(r'\d+', text)
            if numbers:
                return numbers[0]
        return text
