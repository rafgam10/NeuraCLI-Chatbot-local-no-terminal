from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Literal

from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from src.ollama import HistoryEntry

COLORS = {
    "brand": "bold cyan",
    "user": "bold blue",
    "body": "white",
    "muted": "grey70",
    "success": "green",
    "warning": "yellow",
    "error": "red",
}
console = Console(highlight=False)
INPUT_PROMPT = HTML("<prompt>Você › </prompt>")
PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "ansibrightblue bold",
        "completion-menu.completion": "bg:#202632 #d8dee9",
        "completion-menu.completion.current": "bg:#67e8f9 #111827 bold",
        "completion-menu.meta.completion": "bg:#202632 #aeb8c8",
        "completion-menu.meta.completion.current": "bg:#67e8f9 #111827",
    }
)


@dataclass(frozen=True)
class CommandInfo:
    name: str
    description: str
    category: str
    available: bool = True


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size: int | None
    active: bool


def show_header(output: Console, model: str) -> None:
    content = Group(
        Text("Seu assistente local no terminal", style=COLORS["muted"]),
        Text.assemble(("Modelo  ", COLORS["muted"]), (model, "bold white")),
        Text(),
        Text.assemble(
            ("/help", "cyan"),
            (" comandos · ", COLORS["muted"]),
            ("/models", "cyan"),
            (" modelos · ", COLORS["muted"]),
            ("/save", "cyan"),
            (" salvar", COLORS["muted"]),
        ),
    )
    output.print(
        Panel(
            content,
            title=Text.assemble(("NEURA", "bold white"), (" CLI", "bold magenta")),
            title_align="left",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    output.print()


def show_section(output: Console, title: str, subtitle: str = "") -> None:
    output.print()
    output.rule(Text(title, style=COLORS["brand"]), style="cyan")
    if subtitle:
        output.print(Text(subtitle, style=COLORS["muted"]))
    output.print()


def show_notice(
    output: Console,
    title: str,
    message: str,
    *,
    kind: Literal["info", "success", "warning", "error"] = "info",
    details: Sequence[str] = (),
) -> None:
    color = "cyan" if kind == "info" else COLORS[kind]
    icon = {"info": "i", "success": "✓", "warning": "!", "error": "×"}[kind]
    content = Group(
        Text(message, style=COLORS["body"]),
        *(Text(detail, style=COLORS["muted"]) for detail in details),
    )
    output.print(
        Panel(
            content,
            title=Text(f"{icon} {title}", style=f"bold {color}"),
            title_align="left",
            border_style=color,
        )
    )
    output.print()


def show_help(output: Console, commands: Sequence[CommandInfo]) -> None:
    show_section(output, "Central de ajuda", "Comandos locais não são enviados à IA.")
    categories = dict.fromkeys(command.category for command in commands)
    for category in categories:
        output.print(Text(category, style=COLORS["brand"]))
        items = [command for command in commands if command.category == category]
        if output.width < 60:
            for command in items:
                output.print(Text(command.name, style="bold cyan"))
                output.print(Text(command.description, style=COLORS["body"]))
                if not command.available:
                    output.print(Text("Em desenvolvimento", style=COLORS["warning"]))
                output.print()
            continue

        table = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
        table.add_column("Comando", style="cyan", no_wrap=True)
        table.add_column("Descrição", ratio=1)
        table.add_column("Estado")
        for command in items:
            state = (
                Text("Disponível", style=COLORS["success"])
                if command.available
                else Text("Em desenvolvimento", style=COLORS["warning"])
            )
            table.add_row(Text(command.name), Text(command.description), state)
        output.print(table)

    output.print(
        Text(
            "Enter enviar · Tab completar · ↑/↓ histórico de entrada",
            style=COLORS["muted"],
        )
    )
    output.print()


def format_size(size: int | None) -> str:
    if size is None or size < 0:
        return "—"
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return "—"


def show_models(output: Console, models: Sequence[ModelInfo]) -> None:
    total = len(models)
    label = "modelo instalado" if total == 1 else "modelos instalados"
    show_section(output, "Modelos locais", f"{total} {label}")
    if not models:
        show_notice(
            output,
            "Nenhum modelo",
            "Nenhum modelo instalado.",
            kind="warning",
            details=("Instale um modelo usando: ollama pull <nome>",),
        )
        return

    if output.width < 60:
        for model in models:
            output.print(
                Text.assemble(
                    ("● " if model.active else "  ", COLORS["success"]),
                    (model.name, "bold white" if model.active else COLORS["body"]),
                )
            )
            state = "Em uso" if model.active else "Disponível"
            output.print(
                Text(f"  {format_size(model.size)} · {state}", style=COLORS["muted"])
            )
        output.print()
        return

    table = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    table.add_column("Modelo", ratio=1)
    table.add_column("Tamanho", justify="right", no_wrap=True)
    table.add_column("Estado", no_wrap=True)
    for model in models:
        table.add_row(
            Text(model.name, style="bold white" if model.active else COLORS["muted"]),
            Text(format_size(model.size)),
            (
                Text("● Em uso", style=COLORS["success"])
                if model.active
                else Text("Disponível", style=COLORS["muted"])
            ),
        )
    output.print(table)
    output.print()


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Horário indisponível"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return "Horário indisponível"


def show_history(output: Console, history: Sequence[HistoryEntry]) -> None:
    total = len(history)
    label = "interação" if total == 1 else "interações"
    show_section(output, "Histórico da sessão", f"{total} {label}")
    if not history:
        show_notice(
            output,
            "Histórico vazio",
            "Nenhuma mensagem nesta sessão.",
            kind="warning",
        )
        return

    for number, entry in enumerate(history, start=1):
        output.print(
            Panel(
                Text(entry["prompt"], style=COLORS["body"]),
                title=Text(f"#{number} · Você", style=COLORS["user"]),
                title_align="left",
                subtitle=Text(
                    format_timestamp(entry.get("created_at")), style=COLORS["muted"]
                ),
                subtitle_align="right",
                border_style="blue",
            )
        )
        output.print(
            Panel(
                Markdown(
                    entry["response_prompt"], code_theme="monokai", hyperlinks=False
                ),
                title=Text("NeuraCLI", style="bold white"),
                title_align="left",
                border_style="green",
            )
        )
        output.print()


def stream_reply(output: Console, chunks: Iterable[str], model: str) -> None:
    output.print(
        Text.assemble(("NeuraCLI", "bold white"), (f" · {model}", COLORS["muted"]))
    )
    received = False
    if not output.is_terminal or output.is_dumb_terminal:
        try:
            for chunk in chunks:
                if chunk:
                    received = True
                    output.print(Text(chunk), end="", soft_wrap=True)
        finally:
            output.print(end="\n\n")
    else:
        parts: list[str] = []
        last_update = 0.0
        waiting = Spinner("dots", text="Gerando resposta…", style="cyan")
        with Live(waiting, console=output, refresh_per_second=10) as live:
            try:
                for chunk in chunks:
                    if not chunk:
                        continue
                    received = True
                    parts.append(chunk)
                    now = monotonic()
                    if now - last_update >= 0.1:
                        live.update(
                            Markdown(
                                "".join(parts), code_theme="monokai", hyperlinks=False
                            )
                        )
                        last_update = now
            finally:
                live.update(
                    Markdown("".join(parts), code_theme="monokai", hyperlinks=False)
                    if parts
                    else Text()
                )
        output.print()

    if not received:
        show_notice(
            output,
            "Resposta vazia",
            "O modelo não retornou texto. Tente enviar outra mensagem.",
            kind="warning",
        )
