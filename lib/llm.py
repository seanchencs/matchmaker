from typing import Union
from openai import OpenAI
import logging
import json

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LLM')

class LLM:
    def __init__(self, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        """Initialize the LLM client.
        This method sets up a connection to an LLM API service (default: OpenRouter)
        using the provided credentials and configuration.
        Args:
            api_key (str): The API key for authentication
            model (str): The name/identifier of the LLM model to use
            base_url (str, optional): The base URL for the API endpoint. 
                Defaults to "https://openrouter.ai/api/v1"
        Returns:
            None
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
    def generate(self, chat_history: str, prompt: str = '', max_tokens: int = 500, temperature: float = 0.85) -> Union[str, None]:
        """
        Generate text completion using the OpenAI API.
        This method sends a prompt to the OpenAI API and returns the generated text response.
        Args:
            prompt (str): The input prompt text to send to the API
            max_tokens (int, optional): Maximum number of tokens in the generated response. Defaults to 500.
        Returns:
            str: The generated text completion from the API
        Raises:
            openai.APIError: If there is an error communicating with the OpenAI API
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": prompt
                    },
                    {
                        "role": "user",
                        "content": chat_history
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Error generating completion: {e}")
            return None
        logger.debug(f"Generated completion: {completion}")
        if completion.choices:
            return completion.choices[0].message.content
        else:
            return None