import os
import logging
from google import genai
from google.genai import types
from openai import OpenAI

logger = logging.getLogger("eip_mcp_server.generator")

class PlanGenerator:
    def __init__(self, provider: str = "gemini"):
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
            raise ValueError(f"Unknown provider: {provider}")

    def generate_markdown_plan(self, system_prompt: str, context: str, model_name: str = None) -> str:
        """
        Generates a comprehensive Markdown plan using the selected API provider.
        """
        try:
            if self.provider == "gemini":
                model = model_name or "gemini-3.1-pro-preview"
                logger.info(f"Generating plan using Google GenAI: {model}...")
                response = self.gemini_client.models.generate_content(
                    model=model,
                    contents=context,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                return response.text
                
            elif self.provider == "openrouter":
                model = model_name or "meta-llama/llama-3.1-70b-instruct"
                logger.info(f"Generating plan using Meta AI via OpenRouter: {model}...")
                response = self.openrouter_client.chat.completions.create(
                    model=model,
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
