from collections.abc import Iterator
from contextlib import chdir
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from typing import TextIO
import unittest
from unittest.mock import Mock, patch

from ollama import ChatResponse, Message
from rich.console import Console

from src import ui, utils
from src.ollama import HistoryEntry


def history_entry(
    identifier: str, prompt: str = "Oi", response: str = "Olá!"
) -> HistoryEntry:
    return {
        "ID": identifier,
        "created_at": "2026-11-14T12:00:00",
        "prompt": prompt,
        "response_prompt": response,
    }


def response_chunks(text: str) -> Iterator[ChatResponse]:
    yield ChatResponse(message=Message(role="assistant", content=text))


class SaveCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix="neuracli-save-", dir="/tmp/opencode")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / "database.json"
        self.output = StringIO()
        self.console = Console(file=self.output, width=120, color_system=None)

        for replacement in (
            patch.object(utils, "DATABASE_PATH", self.database),
            patch.object(utils, "console", self.console),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def write_database(self, data: object) -> bytes:
        self.database.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        return self.database.read_bytes()

    def read_database(self) -> list[dict[str, object]]:
        return json.loads(self.database.read_text(encoding="utf-8"))

    def assert_failed_without_changes(self, previous: bytes) -> None:
        self.assertEqual(self.database.read_bytes(), previous)
        self.assertIn("Não foi possível salvar", self.output.getvalue())
        self.assertNotIn("salvo com sucesso", self.output.getvalue())
        self.assertEqual(list(self.root.glob(".database.json.*.tmp")), [])

    def test_creates_database_and_preserves_utf8(self) -> None:
        history = [history_entry("new-1", "Olá, tudo bem?", "Você está bem?")]

        utils.command_save(history)

        self.assertEqual(self.read_database(), history)
        self.assertIn("Você está bem?", self.database.read_text(encoding="utf-8"))
        self.assertIn("Prompt salvo com sucesso", self.output.getvalue())
        self.assertEqual(list(self.root.glob(".database.json.*.tmp")), [])

    def test_preserves_legacy_records_even_when_their_numeric_ids_repeat(self) -> None:
        previous = [
            {
                "ID": 1,
                "prompt": "Conversa antiga",
                "response_prompt": "Resposta antiga",
            },
            {"ID": 1, "prompt": "Outra sessão", "response_prompt": "Outra resposta"},
        ]
        self.write_database(previous)
        history = [history_entry("new-1")]

        utils.command_save(history)

        self.assertEqual(self.read_database(), previous + history)

    def test_saving_repeatedly_does_not_duplicate_or_mutate_the_history(self) -> None:
        history = [history_entry("new-1"), history_entry("new-2")]
        original = deepcopy(history)

        utils.command_save(history)
        utils.command_save(history)
        utils.command_save(history)

        self.assertEqual(self.read_database(), history)
        self.assertEqual(history, original)

    def test_adds_only_new_interactions_on_the_next_save(self) -> None:
        history = [history_entry("new-1")]
        utils.command_save(history)
        history.append(history_entry("new-2", "Outra pergunta", "Outra resposta"))

        utils.command_save(history)

        self.assertEqual(self.read_database(), history)

    def test_keeps_identical_conversations_with_different_ids(self) -> None:
        first_session = history_entry("session-a")
        second_session = history_entry("session-b")
        self.write_database([first_session])

        utils.command_save([second_session])

        self.assertEqual(self.read_database(), [first_session, second_session])

    def test_updates_an_existing_id_and_preserves_its_extra_fields(self) -> None:
        previous = dict(history_entry("same-id", response="Resposta antiga"))
        previous["note"] = "Metadado que deve ser preservado"
        self.write_database([previous])
        updated = history_entry("same-id", response="Resposta atualizada")

        utils.command_save([updated])

        self.assertEqual(self.read_database(), [{**previous, **updated}])

    def test_empty_history_does_not_overwrite_existing_data(self) -> None:
        previous = self.write_database([history_entry("old-1")])

        utils.command_save([])

        self.assertEqual(self.database.read_bytes(), previous)
        self.assertIn("Nenhuma conversa nesta sessão", self.output.getvalue())
        self.assertNotIn("salvo com sucesso", self.output.getvalue())

    def test_empty_history_does_not_create_an_empty_database(self) -> None:
        utils.command_save([])

        self.assertFalse(self.database.exists())

    def test_invalid_json_and_invalid_records_are_not_overwritten(self) -> None:
        invalid_contents = [
            "",
            '[{"ID": 1,',
            json.dumps({"history": []}),
            json.dumps(["não é um dicionário"]),
            json.dumps([{"prompt": "Sem ID", "response_prompt": "Resposta"}]),
            json.dumps([{"ID": [], "prompt": "Oi", "response_prompt": "Olá"}]),
            json.dumps([{"ID": True, "prompt": "Oi", "response_prompt": "Olá"}]),
            json.dumps([{"ID": "", "prompt": "Oi", "response_prompt": "Olá"}]),
            json.dumps([{"ID": "old-1", "prompt": 123, "response_prompt": "Olá"}]),
            json.dumps(
                [
                    {
                        "ID": "old-1",
                        "created_at": None,
                        "prompt": "Oi",
                        "response_prompt": "Olá",
                    }
                ]
            ),
        ]

        for contents in invalid_contents:
            with self.subTest(contents=contents):
                self.output.seek(0)
                self.output.truncate()
                self.database.write_text(contents, encoding="utf-8")
                previous = self.database.read_bytes()

                utils.command_save([history_entry("new-1")])

                self.assert_failed_without_changes(previous)

    def test_read_permission_error_preserves_the_database(self) -> None:
        previous = self.write_database([history_entry("old-1")])

        with patch.object(Path, "open", side_effect=PermissionError("Sem permissão")):
            utils.command_save([history_entry("new-1")])

        self.assert_failed_without_changes(previous)

    def test_temporary_file_creation_error_preserves_the_database(self) -> None:
        previous = self.write_database([history_entry("old-1")])

        with patch(
            "src.utils.NamedTemporaryFile", side_effect=PermissionError("Sem permissão")
        ):
            utils.command_save([history_entry("new-1")])

        self.assert_failed_without_changes(previous)

    def test_partial_serialization_failure_preserves_the_database(self) -> None:
        def failed_dump(data: object, file: TextIO, **kwargs: object) -> None:
            file.write("[")
            raise TypeError("Objeto não serializável [created_at]")

        previous = self.write_database([history_entry("old-1")])

        with patch("src.utils.json.dump", side_effect=failed_dump):
            utils.command_save([history_entry("new-1")])

        self.assert_failed_without_changes(previous)

    def test_sync_failure_preserves_the_database(self) -> None:
        previous = self.write_database([history_entry("old-1")])

        with patch("src.utils.os.fsync", side_effect=OSError("Disco cheio")):
            utils.command_save([history_entry("new-1")])

        self.assert_failed_without_changes(previous)

    def test_replacement_failure_preserves_the_database(self) -> None:
        previous = self.write_database([history_entry("old-1")])

        with patch(
            "src.utils.os.replace", side_effect=PermissionError("Sem permissão")
        ):
            utils.command_save([history_entry("new-1")])

        self.assert_failed_without_changes(previous)

    def test_save_command_does_not_call_ollama(self) -> None:
        history = [history_entry("new-1")]

        with patch("src.ollama.chat") as chat_mock:
            with patch("src.utils.ollama.list") as list_mock:
                utils.func_commands("/save", history)

        chat_mock.assert_not_called()
        list_mock.assert_not_called()
        self.assertEqual(self.read_database(), history)

    def test_database_path_does_not_depend_on_the_working_directory(self) -> None:
        other_directory = self.root / "other"
        other_directory.mkdir()
        history = [history_entry("new-1")]

        with chdir(other_directory):
            utils.command_save(history)

        self.assertEqual(self.read_database(), history)
        self.assertFalse((other_directory / "database.json").exists())

    def test_success_is_reported_only_after_atomic_replacement(self) -> None:
        events = []
        real_replace = os.replace

        def replace(source: Path, target: Path) -> None:
            self.assertEqual(source.parent, self.database.parent)
            self.assertEqual(target, self.database)
            real_replace(source, target)
            events.append("replaced")

        def show_notice(*args: object, **kwargs: object) -> None:
            if kwargs.get("kind") == "success":
                events.append("success")

        with (
            patch("src.utils.os.replace", side_effect=replace),
            patch.object(ui, "show_notice", side_effect=show_notice),
        ):
            utils.command_save([history_entry("new-1")])

        self.assertEqual(events, ["replaced", "success"])

    def test_chat_saves_incrementally_without_duplicating_previous_sessions(
        self,
    ) -> None:
        previous = history_entry("previous-session")
        self.write_database([previous])
        session = Mock()
        session.prompt.side_effect = [
            "Oi",
            "/save",
            "/save",
            "Outra pergunta",
            "/save",
            "/exit",
        ]

        with (
            patch.object(sys, "argv", ["run.py", "teste"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", self.console),
            patch(
                "src.ollama.chat",
                side_effect=[
                    response_chunks("Olá!"),
                    response_chunks("Outra resposta"),
                ],
            ) as chat_mock,
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit):
                main["run_chat"]()

        self.assertEqual(chat_mock.call_count, 2)
        current_history = main["ollama_inst"].list_history()
        self.assertEqual(self.read_database(), [previous, *current_history])
        self.assertEqual(self.output.getvalue().count("Prompt salvo com sucesso"), 3)


if __name__ == "__main__":
    unittest.main()
