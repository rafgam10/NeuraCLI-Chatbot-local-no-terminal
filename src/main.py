from rich.console import Console

from prompt_toolkit import PromptSession

from src.utils import list_commands
from src.utils import func_commands

# Instancias:
console = Console()
session:PromptSession[str] = PromptSession(completer=list_commands) 

def run_chat():
    
    console.print("""
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]

           [bold white]N E U R A[/bold white] [bold magenta]C L I[/bold magenta]
      [dim]Seu assistente direto no terminal[/dim]

[bold green]Bem-vindo![/bold green] Vamos transformar ideias em código.

[cyan]›[/cyan] Digite sua mensagem e pressione [bold yellow]Enter[/bold yellow].
[cyan]›[/cyan] Use [bold yellow]Tab[/bold yellow] para completar comandos.
[cyan]›[/cyan] Use [bold yellow]↑ ↓[/bold yellow] para navegar pelo histórico.

[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]
""")
    
    while(True):
        
        
        inputs = session.prompt(console.print("[bold blue]›[/bold blue]Você ↓:")).strip()
        func_commands(inputs)
        console.print(f"[bold green]{inputs}[/bold green]")