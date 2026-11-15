from collections.abc import Iterator
from copy import deepcopy
from io import StringIO
import runpy
import sys
import unittest
from unittest.mock import Mock, patch

from ollama import ChatResponse, ListResponse, Message, ResponseError
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import set_app
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from pydantic import ByteSize
from rich.console import Console
from rich.markdown import Markdown

from src import ui, utils
from src.ollama import HistoryEntry


def history_entry() -> HistoryEntry:
    return {
        "ID": "b4ae62cd-c7c4-459a-8699-083df5048d99",
        "created_at": "2026-11-14T12:34:56",
        "prompt": "[bold]Uma pergunta[/tag-inválida]",
        "response_prompt": "**Uma resposta**\n\n```python\nprint('Olá!')\n```",
    }


class ConsoleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.output = StringIO()
        self.console = Console(file=self.output, width=100, color_system=None)
        replacement = patch.object(utils, "console", self.console)
        replacement.start()
        self.addCleanup(replacement.stop)


class InterfaceTests(ConsoleTestCase):
    def test_header_shows_the_current_model_without_interpreting_markup(self) -> None:
        ui.show_header(self.console, "modelo[teste]:latest")

        text = self.output.getvalue()
        self.assertIn("NEURA CLI", text)
        self.assertIn("modelo[teste]:latest", text)
        self.assertIn("/help", text)
        self.assertIn("/models", text)
        self.assertIn("/save", text)

    def test_notice_messages_and_titles_are_literal_text(self) -> None:
        ui.show_notice(
            self.console,
            "Falha [teste]",
            "[bold green]texto[/bold grenn]",
            kind="error",
            details=("Arquivo: caminho[1]/database.json",),
        )

        text = self.output.getvalue()
        self.assertIn("Falha [teste]", text)
        self.assertIn("[bold green]texto[/bold grenn]", text)
        self.assertIn("caminho[1]/database.json", text)

    def test_help_describes_all_registered_commands_and_their_availability(
        self,
    ) -> None:
        ui.show_help(self.console, utils.COMMANDS)

        text = self.output.getvalue()
        for command in utils.COMMANDS:
            self.assertIn(command.name, text)
        self.assertIn("Geral", text)
        self.assertIn("Conversas", text)
        self.assertIn("Modelos", text)
        self.assertEqual(text.count("Em desenvolvimento"), 2)
        self.assertIn("Tab completar", text)

    def test_history_numbers_interactions_and_keeps_uuid_only_in_data(self) -> None:
        history = [history_entry()]
        previous = deepcopy(history)

        ui.show_history(self.console, history)

        text = self.output.getvalue()
        self.assertIn("#1 · Você", text)
        self.assertIn("14/11/2026 · 12:34", text)
        self.assertIn(history[0]["prompt"], text)
        self.assertIn("Uma resposta", text)
        self.assertIn("print('Olá!')", text)
        self.assertNotIn(history[0]["ID"], text)
        self.assertEqual(history, previous)

    def test_sections_adapt_to_narrow_terminals(self) -> None:
        models = [ui.ModelInfo("um-modelo-com-nome-longo:latest", 2**30, True)]
        for width in (30, 45, 60):
            for section in ("header", "help", "models", "history", "notice"):
                with self.subTest(width=width, section=section):
                    output = StringIO()
                    console = Console(file=output, width=width, color_system=None)
                    if section == "header":
                        ui.show_header(console, models[0].name)
                    elif section == "help":
                        ui.show_help(console, utils.COMMANDS)
                    elif section == "models":
                        ui.show_models(console, models)
                    elif section == "history":
                        ui.show_history(console, [history_entry()])
                    else:
                        ui.show_notice(
                            console, "Aviso", "Um aviso com várias palavras."
                        )

                    self.assertTrue(
                        all(
                            len(line) <= width
                            for line in output.getvalue().splitlines()
                        )
                    )

    def test_size_and_date_formatters_handle_missing_metadata(self) -> None:
        self.assertEqual(ui.format_size(None), "—")
        self.assertEqual(ui.format_size(-1), "—")
        self.assertEqual(ui.format_size(0), "0 B")
        self.assertEqual(ui.format_size(2**30), "1.0 GiB")
        self.assertEqual(ui.format_size(2**50), "1024.0 TiB")
        self.assertEqual(ui.format_timestamp(None), "Horário indisponível")
        self.assertEqual(ui.format_timestamp("data inválida"), "Horário indisponível")

    def test_non_terminal_output_is_streamed_immediately_without_duplicates(
        self,
    ) -> None:
        def chunks() -> Iterator[str]:
            yield "Olá"
            self.assertIn("Olá", self.output.getvalue())
            yield " mundo!"

        ui.stream_reply(self.console, chunks(), "modelo-teste")

        text = self.output.getvalue()
        self.assertEqual(text.count("Olá mundo!"), 1)
        self.assertIn("NeuraCLI · modelo-teste", text)
        self.assertNotIn("Gerando resposta", text)

    def test_terminal_stream_updates_markdown_and_preserves_the_final_response(
        self,
    ) -> None:
        console = Console(file=self.output, force_terminal=True, color_system=None)
        with patch("src.ui.Live") as live_factory:
            with patch("src.ui.monotonic", side_effect=[1.0, 1.2]):
                ui.stream_reply(console, iter(["**Olá", " mundo!**"]), "modelo-teste")

        live = live_factory.return_value.__enter__.return_value
        self.assertGreaterEqual(live.update.call_count, 2)
        final = live.update.call_args.args[0]
        self.assertIsInstance(final, Markdown)
        self.assertEqual(final.markup, "**Olá mundo!**")
        self.assertEqual(live_factory.call_args.kwargs["refresh_per_second"], 10)

    def test_terminal_stream_shows_the_entire_final_response_after_overflow(
        self,
    ) -> None:
        console = Console(
            file=self.output,
            force_terminal=True,
            color_system=None,
            width=60,
            height=4,
        )
        answer = "\n\n".join(f"Linha {number}" for number in range(15))

        ui.stream_reply(console, iter([answer]), "modelo-teste")

        self.assertIn("Linha 14", self.output.getvalue())

    def test_empty_response_shows_a_notice(self) -> None:
        ui.stream_reply(self.console, iter(["", ""]), "modelo-teste")

        self.assertIn("Resposta vazia", self.output.getvalue())

    def test_failed_stream_preserves_partial_output_and_propagates_the_error(
        self,
    ) -> None:
        def chunks() -> Iterator[str]:
            yield "Resposta parcial"
            raise ConnectionError("Conexão perdida")

        with self.assertRaises(ConnectionError):
            ui.stream_reply(self.console, chunks(), "modelo-teste")

        self.assertIn("Resposta parcial", self.output.getvalue())


class CommandInterfaceTests(ConsoleTestCase):
    def test_models_table_uses_current_model_and_normalizes_latest_alias(self) -> None:
        response = ListResponse(
            models=[
                ListResponse.Model(model="llama3.2:latest", size=ByteSize(2**30)),
                ListResponse.Model(model="qwen3.5:4b", size=ByteSize(3 * 2**30)),
            ]
        )
        with patch("src.utils.ollama.list", return_value=response):
            utils.func_commands("/models", model="llama3.2")

        text = self.output.getvalue()
        self.assertIn("Modelos locais", text)
        self.assertIn("llama3.2:latest", text)
        self.assertIn("1.0 GiB", text)
        self.assertEqual(text.count("Em uso"), 1)

    def test_models_handle_empty_results_and_missing_metadata(self) -> None:
        with patch("src.utils.ollama.list", return_value=ListResponse(models=[])):
            utils.command_modals("modelo-teste")
        self.assertIn("Nenhum modelo instalado", self.output.getvalue())

        response = ListResponse(models=[ListResponse.Model()])
        with patch("src.utils.ollama.list", return_value=response):
            utils.command_modals("modelo-teste")
        self.assertIn("Modelo sem nome", self.output.getvalue())

    def test_models_connection_errors_are_shown_without_traceback(self) -> None:
        with patch(
            "src.utils.ollama.list", side_effect=ConnectionError("Falha [teste]")
        ):
            utils.command_modals("modelo-teste")

        text = self.output.getvalue()
        self.assertIn("Não foi possível listar modelos", text)
        self.assertIn("Falha [teste]", text)

    def test_clear_redraws_header_without_mutating_history(self) -> None:
        history = [history_entry()]
        previous = deepcopy(history)

        with patch.object(self.console, "clear") as clear_mock:
            utils.func_commands("/clear", history, model="modelo-atual")

        clear_mock.assert_called_once()
        self.assertEqual(history, previous)
        self.assertIn("modelo-atual", self.output.getvalue())

    def test_pending_commands_are_explicitly_unavailable(self) -> None:
        with patch("src.utils.ollama.list") as list_mock:
            with patch("src.ollama.chat") as chat_mock:
                utils.func_commands("/load")
                utils.func_commands("/model outro-modelo")

        list_mock.assert_not_called()
        chat_mock.assert_not_called()
        text = self.output.getvalue()
        self.assertIn("O comando /load ainda não está disponível.", text)
        self.assertIn("O comando /model ainda não está disponível.", text)

    def test_unknown_commands_produce_a_literal_warning(self) -> None:
        utils.func_commands("/nao-existe[tag]")

        text = self.output.getvalue()
        self.assertIn("Comando desconhecido", text)
        self.assertIn("/nao-existe[tag]", text)
        self.assertIn("/help", text)

    def test_unexpected_arguments_do_not_run_a_command(self) -> None:
        with patch.object(utils, "command_save") as save_mock:
            utils.func_commands("/save argumento")

        save_mock.assert_not_called()
        self.assertIn("Este comando não recebe argumentos", self.output.getvalue())

    def test_command_names_are_case_insensitive(self) -> None:
        utils.func_commands("  /HELP  ")

        self.assertIn("Central de ajuda", self.output.getvalue())

    def test_exit_displays_a_message_and_exits_successfully(self) -> None:
        with self.assertRaises(SystemExit) as error:
            utils.func_commands("/exit")

        self.assertEqual(error.exception.code, 0)
        self.assertIn("Sessão encerrada", self.output.getvalue())


class CompletionInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_requires_slash_and_describes_pending_commands(
        self,
    ) -> None:
        session: PromptSession[str] = PromptSession(
            completer=utils.list_commands,
            input=DummyInput(),
            output=DummyOutput(),
        )
        with set_app(session.app):
            for text, expected in (
                ("", []),
                ("Olá", []),
                ("texto /", []),
                ("/", [command.name for command in utils.COMMANDS]),
                ("/h", ["/help", "/history"]),
                ("/H", ["/help", "/history"]),
                ("/load ", []),
            ):
                with self.subTest(text=text):
                    document = Document(text, cursor_position=len(text))
                    session.default_buffer.document = document
                    completions = list(
                        utils.list_commands.get_completions(document, CompleteEvent())
                    )
                    self.assertEqual([item.text for item in completions], expected)
                    for item in completions:
                        if item.text in ("/load", "/model"):
                            metadata = "".join(
                                fragment[1] for fragment in item.display_meta
                            )
                            self.assertEqual(metadata, "Em desenvolvimento")


class MainInterfaceTests(ConsoleTestCase):
    def test_connection_failure_keeps_the_chat_open_without_recording_a_turn(
        self,
    ) -> None:
        session = Mock()
        session.prompt.side_effect = ["Oi", "/history", "/exit"]
        with (
            patch.object(sys, "argv", ["run.py", "modelo-teste"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", self.console),
            patch(
                "src.ollama.chat", side_effect=ConnectionError("Serviço indisponível")
            ),
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit):
                main["run_chat"]()

        self.assertEqual(main["ollama_inst"].list_history(), [])
        self.assertIn("Não foi possível gerar a resposta", self.output.getvalue())
        self.assertIn("Nenhuma mensagem nesta sessão", self.output.getvalue())
        for call in session.prompt.call_args_list:
            self.assertIs(call.args[0], ui.INPUT_PROMPT)

    def test_missing_model_error_is_reported_without_closing_the_session_abruptly(
        self,
    ) -> None:
        session = Mock()
        session.prompt.side_effect = ["Oi", "/exit"]
        with (
            patch.object(sys, "argv", ["run.py", "modelo-inexistente"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", self.console),
            patch(
                "src.ollama.chat",
                side_effect=ResponseError("Modelo não encontrado", status_code=404),
            ),
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit):
                main["run_chat"]()

        self.assertEqual(main["ollama_inst"].list_history(), [])
        self.assertIn("Modelo não encontrado", self.output.getvalue())

    def test_ctrl_c_cancels_input_and_ctrl_d_exits_cleanly(self) -> None:
        session = Mock()
        session.prompt.side_effect = [KeyboardInterrupt, EOFError]
        with (
            patch.object(sys, "argv", ["run.py", "modelo-teste"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", self.console),
            patch("src.ollama.chat") as chat_mock,
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit) as error:
                main["run_chat"]()

        self.assertEqual(error.exception.code, 0)
        chat_mock.assert_not_called()
        self.assertIn("Entrada cancelada", self.output.getvalue())
        self.assertIn("Sessão encerrada", self.output.getvalue())

    def test_missing_cli_argument_shows_usage_before_opening_the_prompt(self) -> None:
        with (
            patch.object(sys, "argv", ["run.py"]),
            patch("prompt_toolkit.PromptSession") as session_mock,
            patch.object(ui, "console", self.console),
        ):
            with self.assertRaises(SystemExit) as error:
                runpy.run_module("src.main")

        session_mock.assert_not_called()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("Uso: python run.py <modelo>", self.output.getvalue())

    def test_ctrl_c_during_stream_does_not_register_an_incomplete_turn(self) -> None:
        def interrupted_response() -> Iterator[ChatResponse]:
            yield ChatResponse(
                message=Message(role="assistant", content="Resposta parcial")
            )
            raise KeyboardInterrupt

        session = Mock()
        session.prompt.side_effect = ["Oi", "/history", "/exit"]
        with (
            patch.object(sys, "argv", ["run.py", "modelo-teste"]),
            patch("prompt_toolkit.PromptSession", return_value=session),
            patch.object(ui, "console", self.console),
            patch("src.ollama.chat", return_value=interrupted_response()),
        ):
            main = runpy.run_module("src.main")
            with self.assertRaises(SystemExit):
                main["run_chat"]()

        self.assertEqual(main["ollama_inst"].list_history(), [])
        self.assertIn("Resposta parcial", self.output.getvalue())
        self.assertIn("Operação interrompida", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
