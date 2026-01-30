#!/usr/bin/env python3
import unittest
import sys
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Import the module to be tested
import llm_ensemble

class TestLLMEnsemble(unittest.TestCase):
    
    def setUp(self):
        # Reset sys.argv before each test
        self.original_argv = sys.argv
        
    def tearDown(self):
        sys.argv = self.original_argv

    def test_rtf_conversion(self):
        text = "Hello\nWorld"
        rtf = llm_ensemble.text_to_rtf(text)
        self.assertIn(r"{\rtf1", rtf)
        self.assertIn("Hello\\par\nWorld", rtf)

    def test_sanitize_label(self):
        self.assertEqual(llm_ensemble.sanitize_label("gpt-4.0"), "gpt-4.0")
        self.assertEqual(llm_ensemble.sanitize_label("Gemini Pro @ 1.5"), "Gemini_Pro___1.5")

    @patch('argparse.ArgumentParser.parse_args')
    def test_config_parsing(self, mock_parse):
        # Setup mock args
        args = MagicMock()
        args.models = "gemini,codex"
        args.iterations = 3
        args.prompt = "test prompt"
        args.prompt_file = None
        args.positional_prompt = None
        args.outdir = None
        args.gemini_model = "g-model"
        args.codex_model = "c-model"
        args.codex_reasoning = "high"
        args.merge_codex_model = None
        args.merge_reasoning = None
        args.merge_prompt = None
        args.merge_prompt_file = None
        args.timeout = 100
        args.output_format = "txt"
        args.require_git = False
        
        mock_parse.return_value = args
        
        # We manually call parse_args logic if we were testing the parser itself, 
        # but here we test the Config object creation if we extracted it.
        # Instead, let's verify `llm_ensemble.parse_args` logic by mocking sys.argv.
        pass

    def test_arg_parser_logic(self):
        sys.argv = [
            "llm_ensemble.py", 
            "-m", "gemini,codex", 
            "-n", "2", 
            "-p", "Hello"
        ]
        config = llm_ensemble.parse_args()
        self.assertEqual(config.models_csv, "gemini,codex")
        self.assertEqual(config.iterations, 2)
        self.assertEqual(config.prompt_text, "Hello")
        self.assertIsNotNone(config.outdir) # Generated timestamp

    def test_binary_file_detection(self):
        # Mocking prompt file reading
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 10
        # UTF-8 fail, Binary check true
        mock_path.read_text.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'err')
        mock_path.read_bytes.return_value = b'\x00\x01\x02' # contains null
        
        config = MagicMock()
        config.prompt_file = mock_path
        config.outdir = MagicMock()
        
        app = llm_ensemble.EnsembleApp(config)
        
        with self.assertRaises(SystemExit):
            # Suppress stderr for cleaner test output
            with patch('sys.stderr'):
                app.validate_and_setup()

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_gemini_runner(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/gemini"
        
        # Mock file I/O context managers
        with patch('builtins.open', mock_open(read_data='{"response": "AI Answer"}')) as m_open:
            runner = llm_ensemble.GeminiRunner()
            path_in = Path("in.txt")
            path_out = Path("out.txt")
            path_log = Path("log.txt")
            
            success = runner.run(path_in, path_out, path_log, 300, model="my-model")
            
            self.assertTrue(success)
            # Verify command arguments
            args, _ = mock_run.call_args
            cmd = args[0]
            self.assertEqual(cmd, ["gemini", "--output-format", "json", "--model", "my-model"])
            
            # Verify json parsing and writing
            handle = m_open()
            # We expect a write call for the parsed response
            handle.write.assert_any_call("AI Answer")

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_codex_runner(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/codex"
        
        runner = llm_ensemble.CodexRunner()
        path_in = Path("in.txt")
        path_out = Path("out.txt")
        path_log = Path("log.txt")
        
        with patch('builtins.open', mock_open()):
            success = runner.run(path_in, path_out, path_log, 300, 
                                 model="c-model", reasoning="medium", require_git=False)
            
            self.assertTrue(success)
            args, _ = mock_run.call_args
            cmd = args[0]
            # Check for specific flags
            self.assertIn("--skip-git-repo-check", cmd)
            self.assertIn('model_reasoning_effort="medium"', cmd[cmd.index("--config")+1])

    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_parallel_execution(self, MockExecutor):
        # Setup App with mocked config
        config = MagicMock()
        config.models_csv = "gemini:m1"
        config.iterations = 2
        config.outdir = Path("/tmp/out")
        config.gemini_model = "def-gemini"
        config.codex_model = "def-codex"
        config.timeout = 10
        
        app = llm_ensemble.EnsembleApp(config)
        # Manually populate runners list as if validate_and_setup ran
        app.runners_list = [('gemini', 'm1', 'label')]
        app.prompt_canon = Path("/tmp/prompt.txt")
        
        # Mock executor context
        mock_executor_instance = MockExecutor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance
        mock_executor_instance.__exit__.return_value = None
        
        # Mock future
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_executor_instance.submit.return_value = mock_future
        
        # We need to mock as_completed to yield our future twice (since we submitted 2 tasks)
        # In a real scenario, as_completed yields futures as they finish.
        with patch('concurrent.futures.as_completed', return_value=[mock_future, mock_future]):
            results = app.execute_parallel()
            
            self.assertEqual(len(results), 2) # 2 iterations
            self.assertEqual(mock_executor_instance.submit.call_count, 2)

    @patch('llm_ensemble.CodexRunner')
    def test_merge_logic(self, MockCodexRunner):
        config = MagicMock()
        config.outdir = Path("/tmp/test_out")
        config.merge_prompt_file = None
        config.merge_prompt_text = "Custom Merge"
        config.merge_reasoning = "xhigh"
        config.codex_reasoning = "low"
        config.timeout = 300
        config.output_format = "txt"
        config.require_git = False
        
        app = llm_ensemble.EnsembleApp(config)
        app.prompt_canon = MagicMock()
        app.prompt_canon.read_text.return_value = "Original Prompt"
        app.merge_codex_model = "merge-model"
        
        # Mock CodexRunner instance
        mock_runner_inst = MockCodexRunner.return_value
        app.codex_runner = mock_runner_inst
        
        # Mock file writing for merge prompt construction
        with patch('builtins.open', mock_open()) as m_open:
            results = [Path("res1.txt")]
            # We also need to mock reading the result files
            with patch.object(Path, 'read_text', return_value="Candidate 1"):
                with patch.object(Path, 'exists', return_value=True):
                    app.merge(results)
            
            # Verify merge prompt was written
            handle = m_open()
            written_content = "".join(call.args[0] for call in handle.write.call_args_list)
            self.assertIn("Custom Merge", written_content)
            self.assertIn("Original Prompt", written_content)
            self.assertIn("Candidate 1", written_content)
            
            # Verify codex was called for merge
            mock_runner_inst.run.assert_called_once()
            call_args = mock_runner_inst.run.call_args
            self.assertEqual(call_args.kwargs['model'], "merge-model")
            self.assertEqual(call_args.kwargs['reasoning'], "xhigh")

if __name__ == '__main__':
    unittest.main()
