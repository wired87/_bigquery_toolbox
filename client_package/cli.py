import typer
import asyncio
import os
import traceback
from typing import Optional

from .remote_engine import RemoteEngine as CoreEngine
from .rich_manager import ui
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from rich.table import Table

# ip_manager is lightweight, safe to import at top
try:
    from .ip_manager import ip_manager
except ImportError:
    ip_manager = None 

from .speech_handler import SpeechHandler

app = typer.Typer()

def display_welcome():
    ui.display_header("BigQuery AI Toolbox CLI")
    welcome_text = """
    [bold cyan]🚀 Welcome to the Advanced Engine[/bold cyan]
    
    [dim]Powered by Gemini & Vertex AI[/dim]
    
    Available Modes:
    1. [bold green]Chat & Query[/bold green]: Natural language interaction with your data.
    2. [bold blue]Data Ingestion[/bold blue]: Process PDF/CSV/Images from data_dir.
    3. [bold magenta]Vector Search[/bold magenta]: Semantic search over your knowledge base.
    
    [dim]Type 'exit' or 'quit' to leave.[/dim]
    """
    ui.console.print(welcome_text)

def display_query_results(query_result, max_rows=10):
    """
    Display query results as a beautiful Rich table.
    
    Args:
        query_result: List of dictionaries containing query results
        max_rows: Maximum number of rows to display (default: 10)
    """
    if not query_result:
        ui.console.print("[dim]No results returned.[/dim]")
        return
    
    # Limit rows displayed
    results_to_show = query_result[:max_rows]
    total_rows = len(query_result)
    
    # Create table
    table = Table(
        title=f"Query Results ({len(results_to_show)} of {total_rows} rows)",
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        show_lines=False
    )
    
    # Add columns based on first row keys
    if results_to_show:
        for key in results_to_show[0].keys():
            table.add_column(key, style="dim", overflow="fold")
        
        # Add rows
        for row in results_to_show:
            # Convert values to strings and truncate if too long
            row_values = []
            for val in row.values():
                str_val = str(val)
                # Truncate long strings
                if len(str_val) > 50:
                    str_val = str_val[:47] + "..."
                row_values.append(str_val)
            table.add_row(*row_values)
    
    ui.console.print(table)
    
    if total_rows > max_rows:
        ui.console.print(f"[dim]... and {total_rows - max_rows} more rows not shown[/dim]\n")

async def chat_loop():
    """
    Start the AI Chat CLI with Fail-Safe logic.
    """
    display_welcome()
    
    try:
        # 1. Input Phase: Initialization & Auth
        ui.update_state("STARTING", "Initializing Engine...")
        engine = CoreEngine(require_auth=True)
        
        ui.console.print("\n[bold]🔒 Authentication Required[/bold]")
        user_email = os.getenv("CLI_EMAIL", "")
        
        while not engine.is_authenticated:
            # Step A: Email
            if not user_email:
                user_email = Prompt.ask("📧 Enter your [bold cyan]Email[/bold cyan]")
                if "@" not in user_email:
                    ui.update_state("ERROR", "Invalid email format.")
                    user_email = ""
                    continue
                    
            # Step B: Password
            password = Prompt.ask("🔑 Enter your [bold cyan]Password[/bold cyan]", password=True)
            
            async def auth_status(msg, step):
                ui.update_state("PROCESSING", f"{msg} ({step})")
                
            ui.update_state("PROCESSING", "Authenticating...")
            auth_result = await engine.authenticate(user_email, password, status_callback=auth_status)
                
            if auth_result["success"]:
                ui.update_state("SUCCESS", f"{auth_result['message']}")
                ui.console.print(f"[dim]Connected to dataset: {auth_result.get('dataset_id')}[/dim]\n")
            else:
                ui.update_state("ERROR", f"{auth_result['message']}")
                if Confirm.ask("Try again using different email?", default=False):
                    user_email = "" 
                # Loop continues

        # 2. Execution Phase: Main Chat
        use_speech_input = False
        use_speech_output = False
        speech = SpeechHandler(input_enabled=use_speech_input, output_enabled=use_speech_output)
        
        async def status_callback(msg, step):
            ui.update_state("PROCESSING", f"{msg} ({step})")

        async def confirm_callback(msg):
            return Confirm.ask(f"\n{msg}", default=False)

        ui.update_state("SUCCESS", "System Ready! Type your query or <file_path>")

        while True:
            try:
                # Input Handling
                user_input = ""
                
                if use_speech_input:
                    ui.console.print("\n[dim]Press Ctrl+C to switch to text input if stuck.[/dim]")
                    try:
                        user_input = speech.listen()
                    except KeyboardInterrupt:
                        pass
                
                if not user_input:
                    user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
                    
                if user_input.lower() in ['exit', 'quit']:
                    # Clear session history before exit
                    engine.clear_history()
                    ui.update_state("SUCCESS", "Goodbye!")
                    break
                    
                if not user_input.strip():
                    continue
                    
                # Processing Query
                ui.update_state("PROCESSING", "Gemini is thinking...")
                result = await engine.process_user_input(user_input, status_callback=status_callback, confirm_callback=confirm_callback)
                
                # Output Handling
                intent = result.get("intent")
                response_text = result.get("response_text", "")
                
                ui.console.print(f"\n[bold purple]Gemini ({intent})[/bold purple]:")
                ui.console.print(response_text)
                
                # Display query results as table if available
                if result.get("query_result"):
                    ui.console.print("\n")  # Add spacing
                    display_query_results(result["query_result"])
                
                # Traceability
                if result.get("traceability"):
                    ui.console.print(Panel(str(result["traceability"]), title="Traceability", border_style="dim", expand=False))
                
                # Speech Output
                if use_speech_output and response_text:
                    speech.speak(response_text)

            except KeyboardInterrupt:
                ui.update_state("WARNING", "Interrupted by user. Type 'exit' to quit.")
                continue
            except Exception as e:
                ui.handle_error(e, "Chat Loop Processing")

    except Exception as e:
        # 3. Recovery Phase
        ui.handle_error(e, "Global CLI State")
    finally:
        # Always clear history and close connection on exit
        try:
            engine.clear_history()
            await engine.close()  # Gracefully close WebSocket and cleanup
        except:
            pass  # Ignore errors during cleanup
        ui.update_state("SUCCESS", "Clean shutdown complete.")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    BigQuery AI Toolbox CLI Entry Point.
    """
    if ctx.invoked_subcommand is None:
        try:
            asyncio.run(chat_loop())
        except KeyboardInterrupt:
            ui.update_state("SUCCESS", "Exiting...")

@app.command()
def ingest():
    """
    Ingest data from a path with Fail-Safe logic.
    """
    try:
        ui.update_state("STARTING", "Initializing Ingestion Engine...")
        engine = CoreEngine(require_auth=True)
        
        # Auth Logic
        if not engine.is_authenticated:
            email = os.getenv("CLI_EMAIL")
            password = os.getenv("CLI_PASSWORD")
            
            if not email or not password:
                 ui.console.print("\n[bold]🔒 Authentication Required for Ingestion[/bold]")
                 email = Prompt.ask("Email")
                 password = Prompt.ask("Password", password=True)
            
            try:
                 ui.update_state("PROCESSING", "Authenticating...")
                 res = asyncio.run(engine.authenticate(email, password))
                 if not res['success']:
                     ui.update_state("ERROR", f"Authentication failed: {res['message']}")
                     return
            except Exception as e:
                 ui.handle_error(e, "Ingestion Authentication")
                 return
                 
        # Ingestion Configuration Phase
        target_path = Prompt.ask("\n📂 Enter path to file or directory to ingest", default="data_dir")
        
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
        
        async def run_ingest_process():
            async def status_cb(msg, step):
                ui.update_state("PROCESSING", f"{msg} ({step})")
                
            async def confirm_cb(msg):
                return Confirm.ask(f"\n{msg}", default=False)
                
            ui.update_state("STARTING", f"Starting ingestion for: {target_path}")
            result = await engine.ingest_from_path(
                target_path,
                status_callback=status_cb,
                ingestion_config=ingestion_config,
                confirm_callback=confirm_cb
            )
            ui.update_state("SUCCESS", "Ingestion Complete")
            ui.console.print(f"\n[bold green]{result['response_text']}[/bold green]")

        asyncio.run(run_ingest_process())
        
    except Exception as e:
        ui.handle_error(e, "Data Ingestion")

@app.command()
def block_ip(ip: str):
    """
    Block a specific IP address.
    """
    if ip_manager:
        try:
            ip_manager.block_ip(ip)
            ui.update_state("SUCCESS", f"IP {ip} has been blocked.")
        except Exception as e:
            ui.handle_error(e, f"Blocking IP {ip}")
    else:
         ui.update_state("ERROR", "IP Manager not available.")

@app.command()
def unblock_ip(ip: str):
    """
    Unblock a specific IP address.
    """
    if ip_manager:
        try:
            ip_manager.unblock_ip(ip)
            ui.update_state("SUCCESS", f"IP {ip} has been unblocked.")
        except Exception as e:
            ui.handle_error(e, f"Unblocking IP {ip}")
    else:
         ui.update_state("ERROR", "IP Manager not available.")

if __name__ == "__main__":
    app()
