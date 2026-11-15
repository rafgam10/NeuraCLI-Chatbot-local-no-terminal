import sys
import os
import ollama
import json
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from httpx import HTTPError
from prompt_toolkit.application import get_app
from prompt_toolkit.completion import ConditionalCompleter, WordCompleter
from prompt_toolkit.filters import Condition

from src import ui
from src.ollama import HistoryEntry

# Variaveis:
DATABASE_PATH = Path(__file__).resolve().parent.parent / "database.json"
console = ui.console
COMMANDS = (
    ui.CommandInfo("/help", "Exibe os comandos e atalhos disponíveis.", "Geral"),
    ui.CommandInfo("/clear", "Limpa a tela sem apagar a conversa.", "Geral"),
    ui.CommandInfo("/exit", "Encerra o NeuraCLI.", "Geral"),
    ui.CommandInfo("/history", "Exibe as interações desta sessão.", "Conversas"),
    ui.CommandInfo("/save", "Salva o histórico sem duplicar interações.", "Conversas"),
    ui.CommandInfo("/load", "Carrega conversas salvas.", "Conversas", available=False),
    ui.CommandInfo(
        "/models", "Lista os modelos instalados e o modelo ativo.", "Modelos"
    ),
    ui.CommandInfo("/model", "Troca o modelo ativo.", "Modelos", available=False),
)
list_commands = ConditionalCompleter(
    WordCompleter(
        [command.name for command in COMMANDS],
        ignore_case=True,
        sentence=True,
        meta_dict={
            command.name: (
                command.description if command.available else "Em desenvolvimento"
            )
            for command in COMMANDS
        },
    ),
    filter=Condition(
        lambda: get_app().current_buffer.document.text_before_cursor.startswith("/")
    ),
)


# Métodos:
def func_commands(
    input: str,
    history: Sequence[HistoryEntry] = (),
    *,
    model: str | None = None,
) -> None:
    parts = input.strip().split(maxsplit=1)
    if not parts:
        return
    name = parts[0].casefold()
    command = next((item for item in COMMANDS if item.name == name), None)
    if command is None:
        ui.show_notice(
            console,
            "Comando desconhecido",
            f"O comando {parts[0]} não existe.",
            kind="warning",
            details=("Digite /help para consultar os comandos disponíveis.",),
        )
        return
    if not command.available:
        if name == "/load":
            command_load()
        else:
            command_modal()
        return
    if len(parts) > 1:
        ui.show_notice(
            console,
            "Uso do comando",
            "Este comando não recebe argumentos.",
            kind="warning",
            details=(f"Use: {name}",),
        )
        return

    if name == "/exit":
        command_exit()
    elif name == "/help":
        command_help()
    elif name == "/clear":
        console.clear()
        ui.show_header(console, model or "Não informado")
    elif name == "/models":
        command_modals(model)
    elif name == "/history":
        command_history(history)
    elif name == "/save":
        command_save(history)


def command_exit() -> None:
    ui.show_notice(console, "Até logo!", "Sessão encerrada. Até a próxima!")
    sys.exit(0)


def command_help() -> None:
    ui.show_help(console, COMMANDS)


def command_new(): ...


def command_load() -> None:
    ui.show_notice(
        console,
        "Em desenvolvimento",
        "O comando /load ainda não está disponível.",
        kind="warning",
        details=("Suas conversas salvas continuam preservadas no database.json.",),
    )


def command_modal() -> None:
    ui.show_notice(
        console,
        "Em desenvolvimento",
        "O comando /model ainda não está disponível.",
        kind="warning",
        details=("Por enquanto, escolha o modelo ao iniciar: python run.py <modelo>",),
    )


def command_modals(model: str | None = None) -> None:
    try:
        response = ollama.list()
    except (ConnectionError, HTTPError, ollama.ResponseError) as error:
        ui.show_notice(
            console,
            "Não foi possível listar modelos",
            "Verifique se o serviço Ollama está disponível.",
            kind="error",
            details=(str(error),),
        )
        return

    def normalize(name: str) -> str:
        return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"

    active = normalize(model) if model else None
    rows = [
        ui.ModelInfo(
            name=item.model or "Modelo sem nome",
            size=int(item.size) if item.size is not None else None,
            active=item.model is not None and normalize(item.model) == active,
        )
        for item in response.models
    ]
    ui.show_models(console, rows)


def command_history(history: Sequence[HistoryEntry]) -> None:
    ui.show_history(console, history)


def _validate_history_entries(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        raise ValueError("O banco de dados precisa conter uma lista de conversas.")

    entries: list[dict[str, object]] = []
    for position, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"A conversa {position} precisa ser um dicionário.")

        identifier = entry.get("ID")
        if (
            isinstance(identifier, bool)
            or not isinstance(identifier, (str, int))
            or identifier == ""
        ):
            raise ValueError(f"A conversa {position} não tem um ID válido.")

        if not isinstance(entry.get("prompt"), str) or not isinstance(
            entry.get("response_prompt"), str
        ):
            raise ValueError(
                f"A conversa {position} precisa ter pergunta e resposta em texto."
            )

        if "created_at" in entry and not isinstance(entry["created_at"], str):
            raise ValueError(f"A data da conversa {position} precisa estar em texto.")

        entries.append(entry)

    return entries


def command_save(history: Sequence[HistoryEntry]) -> None:
    if not history:
        ui.show_notice(
            console,
            "Nada para salvar",
            "Nenhuma conversa nesta sessão para salvar.",
            kind="warning",
        )
        return

    temporary_path: Path | None = None
    try:
        incoming = _validate_history_entries(list(history))
        try:
            with DATABASE_PATH.open("r", encoding="utf-8") as database_file:
                saved = _validate_history_entries(json.load(database_file))
        except FileNotFoundError:
            saved = []

        positions = {entry["ID"]: index for index, entry in enumerate(saved)}
        for entry in incoming:
            index = positions.get(entry["ID"])
            if index is None:
                positions[entry["ID"]] = len(saved)
                saved.append(dict(entry))
            else:
                saved[index].update(entry)

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATABASE_PATH.parent,
            prefix=f".{DATABASE_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(saved, temporary_file, ensure_ascii=False, indent=4)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # O banco original só é substituído depois que todo o JSON foi gravado.
        os.replace(temporary_path, DATABASE_PATH)
        temporary_path = None
    except (OSError, TypeError, ValueError) as error:
        detail = (
            "O database.json está vazio ou contém JSON inválido."
            if isinstance(error, json.JSONDecodeError)
            else str(error)
        )
        ui.show_notice(
            console,
            "Não foi possível salvar",
            detail,
            kind="error",
            details=("O banco de dados existente não foi alterado.",),
        )
        return
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    total = len(history)
    label = "interação" if total == 1 else "interações"
    ui.show_notice(
        console,
        "Histórico salvo",
        "Prompt salvo com sucesso no banco de dados!",
        kind="success",
        details=(
            f"{total} {label} da sessão · {len(saved)} no banco",
            f"Arquivo: {DATABASE_PATH}",
        ),
    )
