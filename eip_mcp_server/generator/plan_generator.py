import os
import logging
from google import genai
from google.genai import types
from openai import OpenAI

logger = logging.getLogger("eip_mcp_server.generator")

class PlanGenerator:
    def __init__(self, provider: str = "gemini"):
        self.raw_provider = provider
        if provider.startswith("openrouter:"):
            self.provider = "openrouter"
        elif provider.startswith("gemini:"):
            self.provider = "gemini"
        else:
            self.provider = provider
            
        if self.provider == "gemini":
            self.api_key = os.environ.get("GEMINI_API_KEY")
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found in environment, plan generation may fail.")
            else:
                self.gemini_client = genai.Client(api_key=self.api_key)
        elif self.provider == "openrouter":
            self.api_key = os.environ.get("OPENROUTER_API_KEY")
            if not self.api_key:
                logger.warning("OPENROUTER_API_KEY not found in environment, plan generation may fail.")
            
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def generate_markdown_plan(self, system_prompt: str, context: str, model_name: str = None) -> str:
        """
        Generates a comprehensive markdown plan.
        Extracts specific model from provider string if passed like openrouter:anthropic/...
        """
        try:
            if ":" in self.raw_provider and not model_name:
                model_name = self.raw_provider.split(":", 1)[1]
                
            if not model_name:
                raise ValueError("Model must be explicitly selected by the user. No default models are allowed.")

            if self.provider == "gemini":
                logger.info(f"Generating plan using Google AI: {model_name}...")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents=context,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                return response.text
                
            elif self.provider == "openrouter":
                logger.info(f"Generating plan using OpenRouter: {model_name}...")
                response = self.openrouter_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context}
                    ],
                    temperature=0.2,
                    max_tokens=8192,
                )
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Failed to generate plan via {self.provider}: {str(e)}. Falling back to STUB.")
            return f"# STUB Plan\n\nGeneration failed with error: {str(e)}\n\nThis is a fallback stub to ensure the pipeline continues."
