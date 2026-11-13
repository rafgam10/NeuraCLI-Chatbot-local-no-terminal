from ollama import chat, ChatResponse


class Ollama:
    
    def __init__(self, model:str):
        self.history:list = []
        self.model = model
        self._prompt: str | None = None

    
    @property
    def prompt(self) -> str | None:
        return self._prompt

    @prompt.setter
    def prompt(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("prompt deve ser uma string")

        self._prompt = value
        
    def response_prompt(self) -> str | None:
        response:ChatResponse = chat(
            model=self.model,
            messages=[
                {"role": "user", "content": self.prompt},
            ],
            # stream=True
        )
        self.history.append(response.message.content)
        return response.message.content or ""