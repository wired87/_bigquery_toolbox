import sys
import traceback
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text
from rich.theme import Theme
from rich.layout import Layout
from typing import Optional, Dict, Any

# Custom theme for the Toolbox
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "starting": "bold blue",
    "processing": "bold magenta",
})

class RichManager:
    def __init__(self):
        self.console = Console(theme=custom_theme)
        self.live = None
        self.current_task = None
        self.progress = None
        
    def display_header(self, title: str = "BigQuery AI Toolbox"):
        self.console.print(Panel(
            Text(title, justify="center", style="bold cyan"),
            subtitle="Fail-Safe Automation Engine",
            border_style="cyan"
        ))

    def update_state(self, state: str, message: str):
        """
        Updates the UI with the current state: [STARTING], [PROCESSING], [SUCCESS], or [ERROR].
        """
        state_map = {
            "STARTING": "[bold blue][STARTING][/bold blue]",
            "PROCESSING": "[bold magenta][PROCESSING][/bold magenta]",
            "SUCCESS": "[bold green][SUCCESS][/bold green]",
            "ERROR": "[bold red][ERROR][/bold red]",
            "WARNING": "[bold yellow][WARNING][/bold yellow]",
        }
        
        prefix = state_map.get(state.upper(), f"[{state.upper()}]")
        self.console.print(f"{prefix} {message}")

    def handle_error(self, error: Exception, context: str = ""):
        """
        Captures stack trace, logs it, and presents an actionable insight.
        """
        self.update_state("ERROR", f"An error occurred during: {context}")
        
        # Actionable Insights Mapping
        insight = "Check your logs for more details."
        error_str = str(error)
        
        if "websockets.exceptions.ConnectionClosed" in error_str or "ConnectionRefusedError" in error_str:
            insight = "🔌 Server connection lost. Please ensure the backend is running and reachable."
        elif "ModuleNotFoundError" in error_str:
            insight = "📦 Missing dependency. Try running: `pip install -r requirements.txt`"
        elif "google.auth" in error_str or "PermissionDenied" in error_str:
            insight = "🔑 Authentication failed. Verify your Google Cloud credentials and BQ access."
        elif "FileNotFoundError" in error_str:
            insight = "📂 File not found. Check the path and try again."
        elif "quotaExceeded" in error_str or "rateLimitExceeded" in error_str:
            insight = "⏳ API Quota exceeded. Please wait a few minutes or upgrade your tier."
        elif "Invalid WebSocket URL" in error_str:
            insight = "🌐 Server URL configuration error. Check your environment variables or credentials."
        elif "re-upload" in error_str.lower():
            insight = "🔄 Duplicate detected. The system handles this via the confirmation prompt; follow the instructions."
            
        self.console.print(Panel(
            f"[bold red]Error:[/bold red] {error_str}\n\n[bold green]Actionable Insight:[/bold green]\n{insight}",
            title="Recovery Phase",
            border_style="red"
        ))
        
        # Log full traceback to stderr but hidden from main UI if needed, 
        # or just print it if in debug mode.
        # self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    def create_progress(self):
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            transient=True
        )

    def log(self, message: str, style: str = "info"):
        self.console.print(message, style=style)

# Global Instance
ui = RichManager()
