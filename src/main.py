from rich.console import Console
from prompt_toolkit import PromptSession
import sys

from src.ollama import Ollama

from src.utils import list_commands
from src.utils import func_commands

# Instancias:
console = Console()
session:PromptSession[str] = PromptSession(completer=list_commands)

if len(sys.argv) < 2:
    sys.exit("Uso: python run.py <modelo>")
ollama_inst = Ollama(
    model=sys.argv[1]
)

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
        ollama_inst.prompt = inputs
        
        for trecho in ollama_inst.response_prompt():
            console.print(
                trecho,
                end="",
                style="green",
                markup=False,
                highlight=False,
            )
            
        console.print(end="\n\n")
