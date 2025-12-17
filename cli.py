import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
import asyncio
import os
import getpass
import traceback

from remote_engine import RemoteEngine as CoreEngine
# ip_manager is lightweight, safe to import at top
try:
    from ip_manager import ip_manager
except ImportError:
    ip_manager = None # Handle case if file missing during dev

from speech_handler import SpeechHandler

app = typer.Typer()
console = Console()

def display_welcome():
    welcome_text = """
    [bold cyan]🚀 BigQuery AI Toolbox CLI[/bold cyan]
    
    [dim]Powered by Gemini & Vertex AI[/dim]
    
    Available Modes:
    1. [bold green]Chat & Query[/bold green]: Natural language interaction with your data.
    2. [bold blue]Data Ingestion[/bold blue]: Process PDF/CSV/Images from data_dir.
    3. [bold magenta]Vector Search[/bold magenta]: Semantic search over your knowledge base.
    
    [dim]Type 'exit' or 'quit' to leave.[/dim]
    """
    console.print(Panel(welcome_text, border_style="cyan"))

async def chat_loop():
    """
    Start the AI Chat CLI.
    """
    display_welcome()
    
    # 1. Initialize Engine (Auth Required)
    with console.status("[bold green]Initializing Engine...[/bold green]"):
        engine = CoreEngine(require_auth=True) # Enforce Auth
        
    # 2. Authentication Flow
    console.print("\n[bold]🔒 Authentication Required[/bold]")
    user_email = ""
    
    while not engine.is_authenticated:
        # Step A: Email
        if not user_email:
            user_email = Prompt.ask("📧 Enter your [bold cyan]Email[/bold cyan]")
            if "@" not in user_email:
                console.print("[red]Invalid email format.[/red]")
                user_email = ""
                continue
                
        # Step B: Password
        password = Prompt.ask("🔑 Enter your [bold cyan]Password[/bold cyan]", password=True)
        
        with console.status("[bold blue]Authenticating...[/bold blue]"):
            auth_result = await engine.authenticate(user_email, password)
            
        if auth_result["success"]:
            console.print(f"[bold green]{auth_result['message']}[/bold green]")
            console.print(f"[dim]Connected to dataset: {auth_result.get('dataset_id')}[/dim]\n")
        else:
            console.print(f"[bold red]{auth_result['message']}[/bold red]")
            if Confirm.ask("Try again using different email?", default=False):
                user_email = "" 
            # Loop continues

    # 3. Speech Configuration
    use_speech_input = False
    use_speech_output = False
    
    # Optional: confirm speech if desired, defaulting to False for speed
    # use_speech_input = Confirm.ask("🎙️ Enable Speech Input?", default=False) 
    
    speech = SpeechHandler(input_enabled=use_speech_input, output_enabled=use_speech_output)
    
    # Define status callback (Moved up)
    async def status_callback(msg, step):
        console.print(f"[dim]⚙️ {msg} ({step})[/dim]")

    # --- AUTO-INGESTION WORKFLOW ---
    data_dir = os.path.abspath("data_dir")

    ## todo
    if os.path.exists(data_dir) and os.listdir(data_dir):
        console.print(f"\n[bold cyan]📂 Auto-Ingestion Detected[/bold cyan]")
        console.print(f"[dim]Checking {data_dir} for content...[/dim]")
        try:
             with console.status("[bold blue]Processing & Upserting data_dir...[/bold blue]"):
                 logger_msg = await engine.ingest_from_path(data_dir, status_callback=status_callback)
             console.print(f"[bold green]✅ Auto-Ingestion Complete:[/bold green]")
             console.print(logger_msg.get("response_text", "Done."))
        except Exception as e:
             console.print(f"[bold red]❌ Auto-Ingestion Failed: {e}[/bold red]")
             console.print(f"[dim]{traceback.format_exc()}[/dim]")

    # 4. Main Chat Loop
    console.print("[bold green]✅ Ready! Type your query <file_path>[/bold green]")

    while True:
        try:
            # Input Handling
            user_input = ""
            
            if use_speech_input:
                console.print("\n[dim]Press Ctrl+C to switch to text input if stuck.[/dim]")
                try:
                    user_input = speech.listen()
                except KeyboardInterrupt:
                    pass
            
            if not user_input:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
                
            if user_input.lower() in ['exit', 'quit']:
                console.print("[yellow]Goodbye![/yellow]")
                break
                
            if not user_input.strip():
                continue
                
            # --- Handle Slash Commands ---
            if user_input.startswith("/upload"):
                # /upload C:\path\to\file.pdf
                parts = user_input.split(" ", 1)
                if len(parts) < 2:
                    console.print("[red]Usage: /upload <file_path>[/red]")
                    continue
                
                # Strip quotes more robustly
                file_path = parts[1].strip()
                if file_path.startswith('"') and file_path.endswith('"'):
                    file_path = file_path[1:-1]
                elif file_path.startswith("'") and file_path.endswith("'"):
                    file_path = file_path[1:-1]
                    
                if not os.path.exists(file_path):
                    console.print(f"[red]File not found: {file_path}[/red]")
                    continue
                    
                filename = os.path.basename(file_path)
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()

                    with console.status(f"[bold blue]Uploading {filename}...[/bold blue]"):
                        result_msg = await engine.handle_file_upload(filename, content, status_callback=status_callback)
                        
                    console.print(f"[bold green]{result_msg}[/bold green]")
                    
                except Exception as e:
                    console.print(f"[bold red]❌ Upload Error: {e}[/bold red]")
                
                continue

            # Processing Query
            with console.status("[bold blue]Thinking...[/bold blue]"):
                result = await engine.process_user_input(user_input, status_callback=status_callback)
            
            # Output Handling
            intent = result.get("intent")
            response_text = result.get("response_text", "")
            
            console.print(f"\n[bold purple]Gemini ({intent})[/bold purple]:")
            console.print(response_text)
            
            # Traceability
            if result.get("traceability"):
                console.print(Panel(str(result["traceability"]), title="Traceability", border_style="dim", expand=False))
            
            # Speech Output
            if use_speech_output and response_text:
                speech.speak(response_text)

        except KeyboardInterrupt:
            # Allow user to exit with Ctrl+C
            console.print("\n[yellow]Interrupted by user. Type 'exit' to quit.[/yellow]")
            continue
            
        except Exception as e:
            console.print(f"[bold red]❌ Error: {e}[/bold red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    BigQuery AI Toolbox CLI Entry Point.
    """
    if ctx.invoked_subcommand is None:
        try:
            asyncio.run(chat_loop())
        except KeyboardInterrupt:
            console.print("\n[yellow]Exiting...[/yellow]")

@app.command()
def ingest():
    """
    Ingest data from a path.
    Interactive prompts for path and configuration.
    """
    # Initialize Engine
    console.print("[bold green]Initializing Engine for Ingestion...[/bold green]")
    engine = CoreEngine(require_auth=True)
    
    # Auth Logic
    if not engine.is_authenticated:
        # Check Env Vars first for automated flow
        email = os.getenv("CLI_EMAIL")
        password = os.getenv("CLI_PASSWORD")
        
        if not email or not password:
             console.print("\n[bold]🔒 Authentication Required for Ingestion[/bold]")
             email = Prompt.ask("Email")
             password = Prompt.ask("Password", password=True)
        
        try:
             res = asyncio.run(engine.authenticate(email, password))
             if not res['success']:
                 console.print(f"[red]Authentication failed: {res['message']}[/red]")
                 return
        except Exception as e:
             console.print(f"[red]Auth Error: {e}[/red]")
             return
             
    # Ingestion Configuration
    # 1. Path
    target_path = Prompt.ask("\n📂 Enter path to file or directory to ingest", default="data_dir")
    
    # 2. Advanced Settings
    chunk_size = 1000
    overlap = 200
    use_docai = False
    
    if Confirm.ask("⚙️  Configure advanced settings (Chunk size, DocAI)?", default=False):
        chunk_size = IntPrompt.ask("Chunk Size", default=1000)
        overlap = IntPrompt.ask("Chunk Overlap", default=200)
        use_docai = Confirm.ask("Use Google DocAI (OCR)?", default=False)
    
    ingestion_config = {
        "chunk_size": chunk_size,
        "chunk_overlap": overlap,
        "use_docai": use_docai
    }
    
    async def run_ingest():
        async def status_cb(msg, step):
            console.print(f"[dim]{msg}[/dim]")
            
        console.print(f"[bold cyan]🚀 Starting ingestion for: {target_path}[/bold cyan]")
        result = await engine.ingest_from_path(
            target_path,
            status_callback=status_cb,
            ingestion_config=ingestion_config
        )
        console.print(f"\n[bold green]{result['response_text']}[/bold green]")

    asyncio.run(run_ingest())

@app.command()
def block_ip(ip: str):
    """
    Block a specific IP address.
    """
    if ip_manager:
        ip_manager.block_ip(ip)
        console.print(f"[bold red]🚫 IP {ip} has been blocked.[/bold red]")
    else:
         console.print("[red]IP Manager not available.[/red]")

@app.command()
def unblock_ip(ip: str):
    """
    Unblock a specific IP address.
    """
    if ip_manager:
        ip_manager.unblock_ip(ip)
        console.print(f"[bold green]✅ IP {ip} has been unblocked.[/bold green]")
    else:
         console.print("[red]IP Manager not available.[/red]")

if __name__ == "__main__":
    app()
