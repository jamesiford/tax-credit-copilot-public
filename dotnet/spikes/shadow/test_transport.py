"""Network mocks prove refusal before dispatch and bounded, non-exporting consumption."""
import asyncio
from dataclasses import replace
import json
import types
import unittest
from unittest.mock import Mock, patch

import httpx

from catalogue import CASES, Refused
from live import source_reader
from transport import Target, read


class TransportTests(unittest.TestCase):
    def test_compression_and_duplicate_header_bounds_refuse_before_body_consumption(self):
        class Never(httpx.AsyncByteStream):
            async def __aiter__(self):
                raise AssertionError("Refuse before decompressing or reading.")
                yield b""

        async def run():
            for headers in ([("content-type", "application/json"), ("content-encoding", "gzip")],
                            [("content-type", "application/json")] + [("x-duplicate", "x")] * 64):
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, headers=headers, stream=Never()))) as client:
                    with self.assertRaises(Refused):
                        await read(client, Target("http://127.0.0.1:8123", local=True), "health", 1001, 2025)
        asyncio.run(run())

    def test_audited_and_mutating_routes_cannot_reach_transport(self):
        requests = []

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: requests.append(request))) as client:
                for case in ("gateway", "artifact", "ai", "export", "situation", "canonical"):
                    with self.assertRaises(Refused):
                        await read(client, Target("http://127.0.0.1:8123", local=True), case, 1001, 2025)
        asyncio.run(run())
        self.assertFalse(requests)

    def test_row_byte_bounds_and_redirects_do_not_expand_the_catalogue(self):
        async def run():
            async def handle(request):
                return httpx.Response(200, json={"rows": list(range(26))})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=False) as client:
                with self.assertRaises(Refused):
                    await read(client, Target("http://127.0.0.1:8123", local=True), "eligibility", 1001, 2025)
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"value": "x" * 100}))) as client:
                with patch.dict(CASES, {"eligibility": replace(CASES["eligibility"], bytes=64)}), self.assertRaises(Refused):
                    await read(client, Target("http://127.0.0.1:8123", local=True), "eligibility", 1001, 2025)
            calls = []

            def redirect(request):
                calls.append(request)
                return httpx.Response(307, headers={"Location": "https://not-allowed.invalid"}, json={"redirect": True})
            async with httpx.AsyncClient(transport=httpx.MockTransport(redirect), follow_redirects=False) as client:
                row = await read(client, Target("http://127.0.0.1:8123", local=True), "health", 1001, 2025)
            self.assertEqual(307, row["status"])
            self.assertEqual(1, len(calls))
        asyncio.run(run())

    def test_total_deadline_cancels_a_slow_stream(self):
        class Slow(httpx.AsyncByteStream):
            async def __aiter__(self):
                await asyncio.sleep(0.1)
                yield b"{}"

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, headers={"content-type": "application/json"}, stream=Slow()))) as client:
                with patch.dict(CASES, {"health": replace(CASES["health"], seconds=0.01)}), self.assertRaises(TimeoutError):
                    await read(client, Target("http://127.0.0.1:8123", local=True), "health", 1001, 2025)
        asyncio.run(run())

    def test_unknown_or_table_level_write_grants_refuse_and_close_connection(self):
        environment = {"SHADOW_SOURCE_ODBC": "Driver={ODBC Driver 18 for SQL Server};Server=synthetic.invalid;"
                       "Database=synthetic;Encrypt=Yes;TrustServerCertificate=No;ApplicationIntent=ReadOnly",
                       "SHADOW_SOURCE_TOKEN": "synthetic-token", "SHADOW_ACCOUNT": "1001"}
        for rows in ([tuple([0, 1] + [0] * 14 + [None])], [tuple([0, 1] + [0] * 15), (1,)]):
            cursor, connection = Mock(), Mock()
            cursor.execute.return_value = cursor
            cursor.fetchone.side_effect = rows
            connection.cursor.return_value = cursor
            driver = types.SimpleNamespace(connect=Mock(return_value=connection))
            with patch.dict("sys.modules", {"pyodbc": driver}), self.assertRaises(Refused):
                with source_reader(environment):
                    self.fail("Unsafe grants must not expose a fingerprint reader.")
            connection.close.assert_called_once()

    def test_closed_fingerprint_binds_the_account_as_a_parameter(self):
        environment = {"SHADOW_SOURCE_ODBC": "Driver={ODBC Driver 18 for SQL Server};Server=synthetic.invalid;"
                       "Database=synthetic;Encrypt=Yes;TrustServerCertificate=No;ApplicationIntent=ReadOnly",
                       "SHADOW_SOURCE_TOKEN": "synthetic-token", "SHADOW_ACCOUNT": "1001"}
        cursor, connection = Mock(), Mock()
        cursor.execute.return_value = cursor
        cursor.fetchone.side_effect = [tuple([0, 1] + [0] * 15), (0,), (5, "synthetic-modified")]
        connection.cursor.return_value = cursor
        with patch.dict("sys.modules", {"pyodbc": types.SimpleNamespace(connect=Mock(return_value=connection))}):
            with source_reader(environment) as fingerprint:
                self.assertTrue(fingerprint().usable)
        sql, parameter = cursor.execute.call_args.args
        self.assertIn("WHERE [AccountId] = ?", sql)
        self.assertNotIn("1001", sql)
        self.assertEqual(1001, parameter)
        connection.close.assert_called_once()
