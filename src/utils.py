import sys
import os

from prompt_toolkit.completion import WordCompleter
from rich.console import Console

#Variaveis:
console = Console()
list_commands = WordCompleter(
    ["/exit", "/load", "/help", "/models", "/model", "/clear", "/save", "/history",],
    ignore_case=True,
)


#Métodos:
def func_commands(input: str) -> None:
    if input == "/exit":
        command_exit()
    if input == "/help":
        command_help()
    if input == "/clear":
        os.system('cls' if os.name == 'nt' else 'clear')
    

def command_exit() -> None:
    sys.exit()

def command_help() -> None:
    console.print("""
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]
           [bold white]NEURA[/bold white][bold magenta]CLI[/bold magenta] [dim]┃ Central de ajuda[/dim]
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]

[bold yellow]COMANDOS GERAIS[/bold yellow]
  [bold cyan]/help[/bold cyan]      Mostra esta mensagem de ajuda.
  [bold cyan]/clear[/bold cyan]     Limpa a tela do terminal.
  [bold cyan]/exit[/bold cyan]      Encerra o NeuraCLI.

[bold yellow]SUAS CONVERSAS[/bold yellow]
  [bold cyan]/save[/bold cyan]      Salva a conversa atual.
  [bold cyan]/load[/bold cyan]      Carrega uma conversa salva.
  [bold cyan]/history[/bold cyan]   Exibe o histórico de mensagens.

[bold yellow]MODELOS DE IA[/bold yellow]
  [bold cyan]/models[/bold cyan]    Lista os modelos disponíveis.
  [bold cyan]/model[/bold cyan]     Seleciona o modelo da conversa.

[bold green]DICAS RÁPIDAS[/bold green]
  [white]Enter[/white]  [dim]Envia sua mensagem.[/dim]
  [white]Tab[/white]    [dim]Completa comandos.[/dim]
  [white]↑ ↓[/white]    [dim]Navega pelas entradas anteriores.[/dim]

[dim]Para conversar, basta digitar sua mensagem![/dim]
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]
""")

def command_new():
    ...