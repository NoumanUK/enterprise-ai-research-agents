import requests
from typing import Optional


class LLMService:
    """
    Central LLM interface for all agents.

    - Uses Ollama locally
    - Can be swapped later with OpenAI / Claude
    - Keeps agent code clean and independent
    """

    def __init__(
        self,
        model: str = "mistral:latest",
        base_url: str = "http://localhost:11434/api/generate",
        timeout: int = 120
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """
        Send prompt to Ollama and return response text.
        """

        try:
            response = requests.post(
                self.base_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature
                    }
                },
                timeout=self.timeout
            )

            # If Ollama fails
            if response.status_code != 200:
                raise Exception(f"Ollama API Error: {response.text}")

            data = response.json()

            # Safety check (Ollama format sometimes varies)
            if "response" not in data:
                raise Exception(f"Unexpected Ollama response format: {data}")

            return data["response"]

        except requests.exceptions.ConnectionError:
            raise Exception(
                "Cannot connect to Ollama. "
                "Make sure 'ollama serve' is running on localhost:11434"
            )

        except requests.exceptions.Timeout:
            raise Exception(
                "Ollama request timed out. Model might be too slow or overloaded."
            )

        except Exception as e:
            raise Exception(f"LLMService Error: {str(e)}")