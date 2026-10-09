"""Artifact bytes in Azure Blob Storage. [BLOB-1, BLOB-3]

The account has public network access, shared keys and anonymous access all
OFF; the API reaches it over a private endpoint as its managed identity
(Storage Blob Data Contributor at container scope). There is no key and no SAS
anywhere: the API streams bytes itself, so a browser never holds a blob URL.
"""
from __future__ import annotations

import os
from typing import Any


class BlobArtifactStore:
    is_durable = True

    def __init__(self, account_url: str | None = None, credential: Any = None) -> None:
        self.account_url = (account_url or os.getenv("ARTIFACT_BLOB_ACCOUNT_URL") or "").strip()
        if not self.account_url:
            raise ValueError(
                "ARTIFACT_BLOB_ACCOUNT_URL is not set; the blob store refuses to guess an account"
            )
        self._credential = credential
        self._service: Any = None

    def _client(self) -> Any:
        if self._service is None:
            from azure.storage.blob import BlobServiceClient

            credential = self._credential
            if credential is None:
                from azure.identity import DefaultAzureCredential

                credential = DefaultAzureCredential()
            self._service = BlobServiceClient(account_url=self.account_url, credential=credential)
        return self._service

    def put(self, container: str, path: str, data: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        blob = self._client().get_blob_client(container=container, blob=path)
        # overwrite=False: a blob path is never reused, and versioning is on anyway.
        blob.upload_blob(data, overwrite=False, content_settings=ContentSettings(content_type=content_type))

    def get(self, container: str, path: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._client().get_blob_client(container=container, blob=path)
        try:
            return blob.download_blob().readall()
        except ResourceNotFoundError:
            return None
