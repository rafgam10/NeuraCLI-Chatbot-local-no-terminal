from collections.abc import Iterator
from typing import Dict, List, TypedDict
from datetime import datetime
import uuid

from ollama import chat, ChatResponse


class HistoryEntry(TypedDict):
    ID: str
    created_at: str
    prompt: str
    response_prompt: str


class Ollama:
    
    def __init__(self, model:str):
        self.history: List[str] = []
        self.history_prompt: List[HistoryEntry] = []
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
        
        response_text = "".join(partes)
        self.history.append(response_text)
        self.command_history_inst(prompt, response_text)

    def command_history_inst(self, prompt: str, response_prompt: str) -> None:
        self.history_prompt.append(
            {
                "ID": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "prompt": prompt,
                "response_prompt": response_prompt,
            }
        )

    def list_history(self) -> List[HistoryEntry]:
        return self.history_prompt.copy()
