import os
import logging
from openai import OpenAI

logger = logging.getLogger("essot_mcp_server.generator")

class PlanGenerator:
    def __init__(self, provider: str = "openrouter", api_key: str = None):
        self.raw_provider = provider
        if provider.startswith("openrouter:"):
            self.provider = "openrouter"
        else:
            self.provider = provider
            
        if self.provider == "openrouter":
            self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
            if not self.api_key:
                logger.info("OPENROUTER_API_KEY not set locally; plans are generated via the ESSOT Web App PKCE connection.")
                self.openrouter_client = None
            else:
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
            if not self.openrouter_client:
                return (
                    "# Plan Generation Note\n\n"
                    "Plan generation is coordinated through the ESSOT Web App using your linked OpenRouter PKCE connection. "
                    "Trigger generation from the ESSOT Studio or configure OPENROUTER_API_KEY locally for offline agent execution."
                )

            if ":" in self.raw_provider and not model_name:
                model_name = self.raw_provider.split(":", 1)[1]
                
            if not model_name:
                raise ValueError("Model must be explicitly selected by the user. No default models are allowed.")

            if self.provider == "openrouter":
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
