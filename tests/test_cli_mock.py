import unittest
from unittest.mock import MagicMock, patch
import asyncio
import os
import sys

# Add parent directory to path to import cli
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import CoreEngine
# We will patch cli during test execution

class TestCLIWorkflows(unittest.TestCase):

    @patch('cli.console')
    @patch('cli.Prompt.ask')
    @patch('cli.CoreEngine')
    def test_chat_loop_auth_flow(self, mock_engine_cls, mock_prompt, mock_console):
        """
        Test the chat loop authentication and basic exit.
        """
        # Setup Mock Engine
        mock_engine_instance = MagicMock()
        mock_engine_cls.return_value = mock_engine_instance
        
        # Scenario: 
        # 1. Engine init (is_authenticated=False)
        # 2. Prompt for Email -> "test@example.com"
        # 3. Prompt for Password -> "secret"
        # 4. Engine.authenticate -> Success
        # 5. Prompt for Input -> "exit"
        
        # State transitions
        mock_engine_instance.is_authenticated = False
        
        def authenticate_side_effect(email, password):
            mock_engine_instance.is_authenticated = True
            return {"success": True, "message": "Authenticated", "dataset_id": "test_ds"}
            
        mock_engine_instance.authenticate.side_effect = authenticate_side_effect
        
        # Mock Prompts
        # Sequence: Email, Password, Chat Input
        mock_prompt.side_effect = ["test@example.com", "secret", "exit"]
        
        import cli
        # Run async loop
        asyncio.run(cli.chat_loop())
        
        # Assertions
        mock_engine_cls.assert_called_with(require_auth=True)
        # authenticate called
        mock_engine_instance.authenticate.assert_called_with("test@example.com", "secret")
        
    @patch('cli.console')
    @patch('cli.CoreEngine')
    def test_upload_slash_command(self, mock_engine_cls, mock_console):
        """
        Test /upload slash command parsing logic by mocking the loop logic inside a synthetic test.
        Since chat_loop is an infinite loop, we test the logic via the engine directly or simulated input?
        Easier to test the logic if it was a separate function, but since it's in the loop, we'll patch input.
        """
        mock_engine_instance = MagicMock()
        mock_engine_cls.return_value = mock_engine_instance
        mock_engine_instance.is_authenticated = True # Skip auth
        
        # Mock file handling
        with patch('cli.Prompt.ask', side_effect=["/upload \"C:\\fake\\file.pdf\"", "exit"]), \
             patch('builtins.open', unittest.mock.mock_open(read_data=b"data")) as mock_file, \
             patch('os.path.exists', return_value=True):
            
            mock_engine_instance.handle_file_upload.return_value = "Uploaded Successfully"
            
            import cli
            asyncio.run(cli.chat_loop())
            
            # Verify upload called
            args, _ = mock_engine_instance.handle_file_upload.call_args
            self.assertEqual(args[0], "file.pdf") # Basename
            self.assertEqual(args[1], b"data")    # Content

    @patch('cli.console')
    @patch('cli.CoreEngine')
    @patch('cli.Prompt.ask')
    @patch('cli.Confirm.ask')
    @patch('cli.IntPrompt.ask')
    def test_ingest_command(self, mock_int_prompt, mock_confirm, mock_prompt, mock_engine_cls, mock_console):
        """
        Test the ingest subcommand.
        """
        mock_engine_instance = MagicMock()
        mock_engine_cls.return_value = mock_engine_instance
        mock_engine_instance.is_authenticated = True
        
        # Inputs: Path, Confirm Settings, Chunk, Overlap, DocAI
        mock_prompt.return_value = "data_dir"
        mock_confirm.side_effect = [True, True] # Configure settings? Yes. Use DocAI? Yes.
        mock_int_prompt.side_effect = [500, 50] # Chunk, Overlap
        
        mock_engine_instance.ingest_from_path.return_value = {"response_text": "Ingestion Done"}
        
        import cli
        # Call the Typer command function directly
        cli.ingest()
        
        # Check call
        mock_engine_instance.ingest_from_path.assert_called()
        call_args = mock_engine_instance.ingest_from_path.call_args
        # Path
        self.assertEqual(call_args[0][0], "data_dir")
        # Config
        config = call_args[1]['ingestion_config']
        self.assertEqual(config['chunk_size'], 500)
        self.assertEqual(config['chunk_overlap'], 50)
        self.assertEqual(config['use_docai'], True)

if __name__ == '__main__':
    unittest.main()
