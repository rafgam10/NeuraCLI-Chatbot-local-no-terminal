from collections.abc import Iterator

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
        
    def response_prompt(self) -> Iterator[str]:
        prompt = self.prompt
        if prompt is None:
            raise ValueError("Defina o prompt antes de solicitar uma resposta")
        
        response = chat(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt},
            ],
            stream=True,
            think=False,
        )
        
        partes: list[str] = []
        
        for chunk in response:
            texto = chunk.message.content or ""

            if texto:
                partes.append(texto)
                yield texto
        
        self.history.append("".join(partes))