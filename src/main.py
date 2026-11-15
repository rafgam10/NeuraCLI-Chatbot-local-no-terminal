import sys

from httpx import HTTPError
from ollama import ResponseError
from prompt_toolkit import PromptSession

from src import ui
from src.ollama import Ollama
from src.utils import func_commands, list_commands

console = ui.console

if len(sys.argv) < 2:
    ui.show_notice(
        console,
        "Informe um modelo",
        "Uso: python run.py <modelo>",
        kind="warning",
        details=("Consulte os modelos instalados com: ollama list",),
    )
    sys.exit(2)

ollama_inst = Ollama(model=sys.argv[1])
session: PromptSession[str] = PromptSession(
    completer=list_commands,
    complete_while_typing=True,
    style=ui.PROMPT_STYLE,
)


def run_chat() -> None:
    ui.show_header(console, ollama_inst.model)

    while True:
        try:
            inputs = session.prompt(ui.INPUT_PROMPT).strip()
        except KeyboardInterrupt:
            console.print()
            ui.show_notice(
                console,
                "Entrada cancelada",
                "Digite outra mensagem ou use /exit para sair.",
                kind="warning",
            )
            continue
        except EOFError:
            func_commands("/exit", ollama_inst.list_history(), model=ollama_inst.model)
            return

        if not inputs:
            continue

        try:
            if inputs.startswith("/"):
                func_commands(
                    inputs, ollama_inst.list_history(), model=ollama_inst.model
                )
                continue

            ollama_inst.prompt = inputs
            ui.stream_reply(console, ollama_inst.response_prompt(), ollama_inst.model)
        except KeyboardInterrupt:
            ui.show_notice(
                console,
                "Operação interrompida",
                "Você pode continuar conversando. Interações incompletas não são registradas.",
                kind="warning",
            )
        except (ConnectionError, HTTPError, ResponseError) as error:
            ui.show_notice(
                console,
                "Não foi possível gerar a resposta",
                "Verifique a conexão com o Ollama e o nome do modelo.",
                kind="error",
                details=(
                    str(error),
                    "Use /models para consultar os modelos instalados.",
                ),
            )
