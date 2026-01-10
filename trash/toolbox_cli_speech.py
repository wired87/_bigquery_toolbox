import speech_recognition as sr
import pyttsx3
from rich.console import Console

class SpeechHandler:
    def __init__(self, input_enabled: bool = False, output_enabled: bool = False):
        self.console = Console()
        self.input_enabled = input_enabled
        self.output_enabled = output_enabled
        self.recognizer = sr.Recognizer()
        try:
            self.microphone = sr.Microphone() if input_enabled else None
        except Exception as e:
            self.console.print(f"[yellow]⚠️  Microphone Init Failed: {e}[/yellow]")
            self.microphone = None
            self.input_enabled = False
        
        self.engine = None
        if output_enabled:
            try:
                self.engine = pyttsx3.init()
            except Exception as e:
                self.console.print(f"[yellow]⚠️  TTS Engine Init Failed: {e}[/yellow]")
                self.output_enabled = False

    def listen(self) -> str:
        """
        Listens to the microphone and returns the recognized text.
        Returns None if no speech is detected or error occurs.
        """
        if not self.input_enabled or not self.microphone:
            return None

        with self.microphone as source:
            self.console.print("[dim]🎤 Listening...[/dim]", end="\r")
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                self.console.print("[dim]⚡ Processing...[/dim]", end="\r")
                text = self.recognizer.recognize_google(audio)
                self.console.print(f"[bold cyan]🎤 You said: {text}[/bold cyan]")
                return text
            except sr.WaitTimeoutError:
                return None
            except sr.UnknownValueError:
                # self.console.print("[dim]🤷 Could not understand audio[/dim]")
                return None
            except sr.RequestError as e:
                self.console.print(f"[red]❌ Speech Service Error: {e}[/red]")
                return None
            except Exception as e:
                self.console.print(f"[red]❌ Microphone Error: {e}[/red]")
                return None

    def speak(self, text: str):
        """
        Reads the text aloud.
        """
        if not self.output_enabled or not self.engine:
            return

        try:
            # Clean text (remove markdown mostly)
            clean_text = text.replace("*", "").replace("#", "")
            self.engine.say(clean_text)
            self.engine.runAndWait()
        except Exception as e:
            self.console.print(f"[yellow]⚠️  TTS Error: {e}[/yellow]")
