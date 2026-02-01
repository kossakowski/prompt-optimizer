import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from pathlib import Path
import json
import zipfile

# Ensure the script can be imported
sys.path.append(os.getcwd())
import prompt_optimizer

class TestUtils(unittest.TestCase):
    def test_sanitize_label(self):
        self.assertEqual(prompt_optimizer.sanitize_label("Hello World!"), "Hello_World_")
        self.assertEqual(prompt_optimizer.sanitize_label("test-file.txt"), "test-file.txt")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_extract_text_from_pdf_success(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/pdftotext"
        mock_run.return_value.stdout = "PDF Content"
        path = Path("test.pdf")
        
        result = prompt_optimizer.extract_text_from_pdf(path)
        self.assertEqual(result, "PDF Content")
        mock_run.assert_called_once()

    @patch("shutil.which")
    def test_extract_text_from_pdf_missing_tool(self, mock_which):
        mock_which.return_value = None
        path = Path("test.pdf")
        result = prompt_optimizer.extract_text_from_pdf(path)
        self.assertIn("Missing 'pdftotext'", result)

    def test_extract_text_from_docx(self):
        # Create a dummy valid docx structure in memory is hard with zipfile.ZipFile requiring a file-like object
        # We will mock zipfile.ZipFile
        with patch("zipfile.ZipFile") as mock_zip:
            mock_zf = MagicMock()
            mock_zip.return_value.__enter__.return_value = mock_zf
            
            # minimal word/document.xml - kept on one line to avoid syntax headaches
            xml_content = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:t>Hello DOCX</w:t></w:p></w:body></w:document>'
            
            mock_zf.read.return_value = xml_content
            
            path = Path("test.docx")
            result = prompt_optimizer.extract_text_from_docx(path)
            self.assertEqual(result, "Hello DOCX")

    @patch("prompt_optimizer.extract_text_from_pdf")
    def test_process_context_files(self, mock_pdf):
        mock_pdf.return_value = "PDF_TEXT"
        
        with patch("pathlib.Path.read_bytes", return_value=b"TXT_TEXT"), \
             patch("pathlib.Path.exists", return_value=True):
            
            f1 = Path("a.pdf")
            f2 = Path("b.txt")
            
            result = prompt_optimizer.process_context_files([f1, f2])
            
            self.assertIn("PDF_TEXT", result)
            self.assertIn("TXT_TEXT", result)
            self.assertIn("[Context File: a.pdf]", result)

class TestPromptConstruction(unittest.TestCase):
    def test_construct_meta_prompt_simple(self):
        draft = "Fix my code"
        context = ""
        model = "gemini-pro"
        
        prompt = prompt_optimizer.construct_meta_prompt(draft, context, model)
        
        self.assertIn("gemini-pro", prompt)
        self.assertIn("Fix my code", prompt)
        self.assertNotIn("Attached Background Context", prompt)

    def test_construct_meta_prompt_with_context(self):
        draft = "Fix my code"
        context = "Here is the code"
        model = "gemini-pro"
        
        prompt = prompt_optimizer.construct_meta_prompt(draft, context, model)
        
        self.assertIn("Attached Background Context", prompt)
        self.assertIn("Here is the code", prompt)

    def test_construct_refinement_prompt(self):
        prev = "Old Prompt"
        feedback = "Make it better"
        
        prompt = prompt_optimizer.construct_refinement_prompt(prev, feedback)
        
        self.assertIn("Old Prompt", prompt)
        self.assertIn("Make it better", prompt)

class TestRunners(unittest.TestCase):
    @patch("subprocess.run")
    def test_gemini_runner_success(self, mock_run):
        runner = prompt_optimizer.GeminiRunner()
        
        # Mock file operations since runner reads/writes files
        with patch("builtins.open", mock_open()) as mocked_file:
            # We need to handle multiple file opens.
            # The runner opens: prompt (r), json_out (w), log (w), json_out (r), output (w)
            
            # Setup the read on json_out to return valid json
            # We need side_effect for open to handle different files?
            # Or simpler: just ensure subprocess is called correctly and we don't crash.
            # Ideally we mock json.load too.
            
            with patch("json.load", return_value={"response": "Optimized Prompt"}):
                mock_run.return_value.returncode = 0
                
                res = runner.run(Path("in.prompt"), Path("out.txt"), Path("log.txt"), "model-v1")
                
                self.assertTrue(res)
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                self.assertIn("gemini", args)
                self.assertIn("--model", args)

    @patch("subprocess.run")
    def test_codex_runner_success(self, mock_run):
        runner = prompt_optimizer.CodexRunner()
        
        with patch("builtins.open", mock_open()):
             mock_run.return_value.returncode = 0
             res = runner.run(Path("in.prompt"), Path("out.txt"), Path("log.txt"), "model-v1", "high")
             
             self.assertTrue(res)
             mock_run.assert_called_once()
             args = mock_run.call_args[0][0]
             self.assertIn("codex", args)
             # Index might be different depending on arg construction order, but 'codex' is [0]
             # Just check if 'high' is in one of the args string
             found_reasoning = False
             for arg in args:
                 if 'model_reasoning_effort="high"' in arg:
                     found_reasoning = True
                     break
             self.assertTrue(found_reasoning)

if __name__ == "__main__":
    unittest.main()