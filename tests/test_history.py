from collections.abc import Iterator
from copy import deepcopy
from datetime import datetime
from io import StringIO
import runpy
import sys
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from ollama import ChatResponse, Message
from rich.console import Console

from src.ollama import HistoryEntry, Ollama
from src import ui, utils


def response_chunks(*parts: str | None) -> Iterator[ChatResponse]:
    for part in parts:
        yield ChatResponse(message=Message(role="assistant", content=part))


def history_entry(identifier: str, prompt: str, response: str) -> HistoryEntry:
    return {
        "ID": identifier,
        "created_at": "2026-11-14T12:00:00",
        "prompt": prompt,
        "response_prompt": response,
    }


class OllamaHistoryTests(unittest.TestCase):
    def test_preserves_multiple_interactions_and_joins_streamed_chunks(self) -> None:
        bot = Ollama(model="teste")
        self.assertEqual(bot.list_history(), [])

        with patch(
            "src.ollama.chat",
            side_effect=[
                response_chunks("O", None, "lá!", ""),
                response_chunks("Python é ", "uma linguagem."),
            ],
        ) as chat_mock:
            bot.prompt = "Oi"
            self.assertEqual(list(bot.response_prompt()), ["O", "lá!"])
            bot.prompt = "O que é Python?"
            self.assertEqual(
                list(bot.response_prompt()), ["Python é ", "uma linguagem."]
            )

        self.assertEqual(chat_mock.call_count, 2)
        self.assertEqual(bot.history, ["Olá!", "Python é uma linguagem."])
        history = bot.list_history()
        self.assertEqual(
            [(entry["prompt"], entry["response_prompt"]) for entry in history],
            [("Oi", "Olá!"), ("O que é Python?", "Python é uma linguagem.")],
        )
        self.assertEqual(len({entry["ID"] for entry in history}), 2)
        for entry in history:
            self.assertEqual(str(UUID(entry["ID"])), entry["ID"])
            self.assertIsInstance(datetime.fromisoformat(entry["created_at"]), datetime)

    def test_registers_interaction_only_after_stream_finishes(self) -> None:
        bot = Ollama(model="teste")
        bot.prompt = "Pergunta"

        with patch("src.ollama.chat", return_value=response_chunks("Parte 1", " e 2")):
            stream = bot.response_prompt()
            self.assertEqual(next(stream), "Parte 1")
            self.assertEqual(bot.list_history(), [])
            self.assertEqual(list(stream), [" e 2"])

        self.assertEqual(bot.list_history()[0]["response_prompt"], "Parte 1 e 2")

    def test_failed_stream_does_not_register_a_completed_interaction(self) -> None:
        def failed_response() -> Iterator[ChatResponse]:
            yield from response_chunks("Resposta parcial")
            raise ConnectionError("Conexão interrompida")

        bot = Ollama(model="teste")
        bot.prompt = "Pergunta"

        with patch("src.ollama.chat", return_value=failed_response()):
            with self.assertRaises(ConnectionError):
                list(bot.response_prompt())

        self.assertEqual(bot.list_history(), [])
        self.assertEqual(bot.history, [])

    def test_history_list_is_a_snapshot(self) -> None:
        bot = Ollama(model="teste")
        bot.command_history_inst("Pergunta", "Resposta")

        snapshot = bot.list_history()
        snapshot.clear()

        self.assertEqual(len(bot.list_history()), 1)


class HistoryInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output = StringIO()
        console = Console(file=self.output, width=80, color_system=None)
        console_patch = patch.object(utils, "console", console)
        console_patch.start()
        self.addCleanup(console_patch.stop)

    def test_empty_history_shows_notice(self) -> None:
        utils.command_history([])

        output = self.output.getvalue()
        self.assertIn("Histórico da sessão", output)
        self.assertIn("Nenhuma mensagem nesta sessão.", output)

    def test_shows_all_interactions_in_order_without_mutating_history(self) -> None:
        history: list[HistoryEntry] = [
            history_entry("1", "Primeira pergunta", "Resposta 1"),
            history_entry("2", "Segunda pergunta", "Resposta 2"),
        ]
        original_history = deepcopy(history)

        utils.command_history(history)

        output = self.output.getvalue()
        self.assertIn("2 interações", output)
        self.assertIn("#1 · Você", output)
        self.assertIn("#2 · Você", output)
        self.assertEqual(output.count("NeuraCLI"), 2)
        self.assertLess(output.index("Primeira pergunta"), output.index("Resposta 1"))
        self.assertLess(output.index("Resposta 1"), output.index("Segunda pergunta"))
        self.assertLess(output.index("Segunda pergunta"), output.index("Resposta 2"))
        self.assertEqual(history, original_history)

    def test_message_markup_is_displayed_literally(self) -> None:
        history: list[HistoryEntry] = [
            history_entry(
                "1",
                "[bold green]teste[/bold grenn]",
                "Use lista[0] e [tags] como texto.\nOutra linha.",
            )
        ]

        utils.command_history(history)

        output = self.output.getvalue()
        self.assertIn("1 interação", output)
        self.assertNotIn("1 interações", output)
        self.assertIn(history[0]["prompt"], output)
        self.assertIn("Use lista[0] e [tags] como texto.", output)
        self.assertIn("Outra linha.", output)

    def test_history_command_does_not_call_ollama(self) -> None:
        with patch("src.ollama.chat") as chat_mock:
            with patch("src.utils.ollama.list") as list_mock:
                utils.func_commands("/history", [])

        chat_mock.assert_not_called()
        list_mock.assert_not_called()
        self.assertIn("Nenhuma mensagem nesta sessão.", self.output.getvalue())

    def test_panels_wrap_on_a_narrow_terminal(self) -> None:
        history: list[HistoryEntry] = [
            history_entry(
                "1",
                "Uma pergunta longa que precisa ser quebrada em várias linhas.",
                "Uma resposta longa que também precisa ser quebrada.",
            )
        ]
        console = Console(file=self.output, width=30, color_system=None)

        with patch.object(utils, "console", console):
            utils.command_history(history)

        lines = self.output.getvalue().splitlines()
        self.assertTrue(all(len(line) <= 30 for line in lines))


class HistoryIntegrationTests(unittest.TestCase):
    def test_history_command_reads_the_current_chat_session(self) -> None:
        output = StringIO()
        console = Console(file=output, width=80, color_system=None)
        session = Mock()
        session.prompt.side_effect = ["", "/history", "Olá", "/history", "/exit"]

        with (
            patch.object(sys, "argv", ["run.py", "teste"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", console),
            patch.object(utils, "console", console),
            patch(
                "src.ollama.chat", return_value=response_chunks("Olá", "!")
            ) as chat_mock,
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit):
                main["run_chat"]()

        chat_mock.assert_called_once_with(
            model="teste",
            messages=[{"role": "user", "content": "Olá"}],
            stream=True,
            think=False,
        )
        history = main["ollama_inst"].list_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["prompt"], "Olá")
        self.assertEqual(history[0]["response_prompt"], "Olá!")
        self.assertEqual(str(UUID(history[0]["ID"])), history[0]["ID"])
        self.assertIsInstance(
            datetime.fromisoformat(history[0]["created_at"]), datetime
        )
        self.assertIn("Nenhuma mensagem nesta sessão.", output.getvalue())
        self.assertIn("1 interação", output.getvalue())


if __name__ == "__main__":
    unittest.main()
