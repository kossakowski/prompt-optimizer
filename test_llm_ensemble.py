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
        # Verify it starts with Outputs/
        self.assertTrue(str(config.outdir).startswith("Outputs/llm_ensemble_"))

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

    def test_context_file_processing(self):
        # Mock config
        config = MagicMock()
        config.outdir = MagicMock(spec=Path)
        config.prompt_text = "Main Prompt"
        config.prompt_file = None
        config.models_csv = "gemini" # minimal valid
        config.iterations = 1
        config.gemini_model = "gemini-default"
        config.codex_model = "codex-default"
        
        # Mock context files
        ctx1 = MagicMock(spec=Path)
        ctx1.exists.return_value = True
        ctx1.name = "ctx1.txt"
        ctx1.read_bytes.return_value = b"Context One Content"
        
        ctx2 = MagicMock(spec=Path)
        ctx2.exists.return_value = True
        ctx2.name = "ctx2.py"
        ctx2.read_bytes.return_value = b"def foo(): pass"
        
        config.context_files = [ctx1, ctx2]
        
        app = llm_ensemble.EnsembleApp(config)
        
        # Mock output file creation (prompt.txt)
        mock_prompt_canon = MagicMock()
        config.outdir.__truediv__.return_value = mock_prompt_canon
        
        # Mock dependencies check to avoid system calls
        app.gemini_runner = MagicMock()
        app.gemini_runner.check_dependency.return_value = True
        app.codex_runner = MagicMock()
        app.codex_runner.check_dependency.return_value = True
        
        app.validate_and_setup()
        
        # Verify content written to prompt.txt
        mock_prompt_canon.write_text.assert_called_once()
        written_content = mock_prompt_canon.write_text.call_args[0][0]
        
        self.assertIn("[Context File: ctx1.txt]", written_content)
        self.assertIn("Context One Content", written_content)
        self.assertIn("[Context File: ctx2.py]", written_content)
        self.assertIn("def foo(): pass", written_content)
        self.assertIn("USER PROMPT:", written_content)
        self.assertIn("Main Prompt", written_content)

    @patch('shutil.which')
    @patch('subprocess.run')
    def test_pdf_context_extraction(self, mock_run, mock_which):
        # Setup
        mock_which.return_value = "/usr/bin/pdftotext"
        
        config = MagicMock()
        config.outdir = MagicMock(spec=Path)
        config.prompt_text = "Prompt"
        config.prompt_file = None
        config.models_csv = "gemini"
        config.iterations = 1
        config.gemini_model = "g"
        config.codex_model = "c"
        
        # Mock PDF file
        pdf_file = MagicMock(spec=Path)
        pdf_file.exists.return_value = True
        pdf_file.name = "document.pdf"
        pdf_file.suffix = ".pdf"
        
        config.context_files = [pdf_file]
        
        app = llm_ensemble.EnsembleApp(config)
        app.gemini_runner = MagicMock()
        app.gemini_runner.check_dependency.return_value = True
        app.codex_runner = MagicMock()
        app.codex_runner.check_dependency.return_value = True
        
        # Mock pdftotext output
        mock_run.return_value.stdout = "Extracted PDF Text"
        
        # Mock prompt writer
        mock_prompt_canon = MagicMock()
        config.outdir.__truediv__.return_value = mock_prompt_canon
        
        app.validate_and_setup()
        
        # Verify pdftotext was called
        mock_run.assert_called_with(
            ["pdftotext", "-layout", str(pdf_file), "-"],
            capture_output=True, text=True, check=True
        )
        
        # Verify text is in prompt
        written_content = mock_prompt_canon.write_text.call_args[0][0]
        self.assertIn("[Context File: document.pdf]", written_content)
        self.assertIn("Extracted PDF Text", written_content)

    @patch('zipfile.ZipFile')
    def test_docx_context_extraction(self, MockZipFile):
        # Mock DOCX content (Word XML structure)
        xml_content = b"""
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:r><w:t>Hello</w:t></w:r>
                    <w:r><w:t> </w:t></w:r>
                    <w:r><w:t>World</w:t></w:r>
                </w:p>
                <w:p>
                    <w:r><w:t>Paragraph 2</w:t></w:r>
                </w:p>
            </w:body>
        </w:document>
        """
        
        # Setup ZipFile Mock
        mock_zip = MockZipFile.return_value.__enter__.return_value
        mock_zip.read.return_value = xml_content
        
        # Setup Config
        config = MagicMock()
        config.outdir = MagicMock(spec=Path)
        config.prompt_text = "Prompt"
        config.prompt_file = None
        config.models_csv = "gemini"
        config.iterations = 1
        config.gemini_model = "g"
        config.codex_model = "c"
        
        docx_file = MagicMock(spec=Path)
        docx_file.exists.return_value = True
        docx_file.name = "test.docx"
        docx_file.suffix = ".docx"
        
        config.context_files = [docx_file]
        
        app = llm_ensemble.EnsembleApp(config)
        app.gemini_runner = MagicMock()
        app.codex_runner = MagicMock()
        app.gemini_runner.check_dependency.return_value = True
        app.codex_runner.check_dependency.return_value = True
        
        # Mock prompt writer
        mock_prompt_canon = MagicMock()
        config.outdir.__truediv__.return_value = mock_prompt_canon
        
        app.validate_and_setup()
        
        # Verify
        mock_zip.read.assert_called_with('word/document.xml')
        
        written_content = mock_prompt_canon.write_text.call_args[0][0]
        self.assertIn("[Context File: test.docx]", written_content)
        # The extractor joins text parts in a paragraph, and paragraphs with newlines
        self.assertIn("Hello World", written_content) 
        self.assertIn("Paragraph 2", written_content)

    @patch('shutil.which')
    @patch('subprocess.run')
    @patch('zipfile.ZipFile')
    def test_multiple_mixed_context_files(self, MockZipFile, mock_run, mock_which):
        """Verify that Text, PDF, and DOCX files are all processed and combined correctly."""
        # 1. Setup PDF Tools
        mock_which.return_value = "/usr/bin/pdftotext"
        mock_run.return_value.stdout = "CONTENT_FROM_PDF"
        
        # 2. Setup DOCX Tools
        mock_zip = MockZipFile.return_value.__enter__.return_value
        mock_zip.read.return_value = b"""
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body><w:p><w:r><w:t>CONTENT_FROM_DOCX</w:t></w:r></w:p></w:body>
        </w:document>
        """
        
        # 3. Setup Files
        ctx_txt = MagicMock(spec=Path); ctx_txt.exists.return_value = True; ctx_txt.name = "f1.txt"; ctx_txt.suffix = ".txt"
        ctx_txt.read_bytes.return_value = b"CONTENT_FROM_TXT"
        
        ctx_pdf = MagicMock(spec=Path); ctx_pdf.exists.return_value = True; ctx_pdf.name = "f2.pdf"; ctx_pdf.suffix = ".pdf"
        
        ctx_docx = MagicMock(spec=Path); ctx_docx.exists.return_value = True; ctx_docx.name = "f3.docx"; ctx_docx.suffix = ".docx"
        
        # 4. Config
        config = MagicMock()
        config.outdir = MagicMock(spec=Path)
        config.prompt_text = "MAIN_PROMPT"
        config.prompt_file = None
        config.models_csv = "gemini"; config.gemini_model = "g"; config.codex_model = "c"
        config.iterations = 1
        config.context_files = [ctx_txt, ctx_pdf, ctx_docx]
        
        # 5. Run
        app = llm_ensemble.EnsembleApp(config)
        app.gemini_runner = MagicMock()
        app.gemini_runner.check_dependency.return_value = True
        app.codex_runner = MagicMock()
        app.codex_runner.check_dependency.return_value = True
        
        mock_prompt_canon = MagicMock()
        config.outdir.__truediv__.return_value = mock_prompt_canon
        
        app.validate_and_setup()
        
        # 6. Verify Final Prompt Content
        full_text = mock_prompt_canon.write_text.call_args[0][0]
        
        self.assertIn("[Context File: f1.txt]", full_text)
        self.assertIn("CONTENT_FROM_TXT", full_text)
        
        self.assertIn("[Context File: f2.pdf]", full_text)
        self.assertIn("CONTENT_FROM_PDF", full_text)
        
        self.assertIn("[Context File: f3.docx]", full_text)
        self.assertIn("CONTENT_FROM_DOCX", full_text)
        
        self.assertIn("USER PROMPT:", full_text)
        self.assertIn("MAIN_PROMPT", full_text)

    def test_fallback_encoding(self):
        """Verify that non-UTF8 text files are read using Latin-1 fallback."""
        # Create a mock file that raises UnicodeDecodeError on utf-8 read
        bad_file = MagicMock(spec=Path)
        bad_file.exists.return_value = True
        bad_file.name = "latin1.txt"
        bad_file.suffix = ".txt"
        
        # Byte sequence invalid in UTF-8 (e.g., standalone 0xE9 which is 'é' in Latin-1)
        latin_bytes = b"\xE9" 
        bad_file.read_bytes.return_value = latin_bytes
        
        config = MagicMock()
        config.outdir = MagicMock(spec=Path)
        config.prompt_text = "Prompt"
        config.prompt_file = None
        config.context_files = [bad_file]
        config.models_csv = "gemini"; config.gemini_model = "g"; config.codex_model = "c"; config.iterations = 1

        app = llm_ensemble.EnsembleApp(config)
        app.gemini_runner = MagicMock(); app.codex_runner = MagicMock()
        app.gemini_runner.check_dependency.return_value = True
        app.codex_runner.check_dependency.return_value = True
        
        mock_prompt_canon = MagicMock()
        config.outdir.__truediv__.return_value = mock_prompt_canon
        
        app.validate_and_setup()
        
        full_text = mock_prompt_canon.write_text.call_args[0][0]
        # In Latin-1, 0xE9 is 'é'. If fallback works, we see 'é'.
        self.assertIn("é", full_text)
        self.assertIn("[Context File: latin1.txt]", full_text)

if __name__ == '__main__':
    unittest.main()
