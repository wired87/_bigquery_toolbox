# Unused Python Classes in Trash Directory

The following classes were identified within the `trash` directory. No usages of these specific class definitions were found in the active codebase (excluding `trash` itself).

## 1. CLI / Utility Classes

| Class Name | File(s) | Notes |
| :--- | :--- | :--- |
| `SpeechHandler` | `trash/toolbox_cli_speech.py`<br>`trash/root_speech_deprecated.py` | Active replacement exists in `client_package/speech_handler.py` |
| `Interactor` | `trash/toolbox_cli_interactor.py` | |
| `ServerConfig` | `trash/server_config.py` | |
| `GlobalServerConfig` | `trash/server_config.py` | Commented out references found in `client_package/app.py` |
| `RemoteEngine` | `trash/remote_engine.py`<br>`trash/client_remote_engine_deprecated.py` | |
| `IpManager` | `trash/ip_manager.py`<br>`trash/ip_manager_client.py` | |

## 2. Django/Web Backend Classes (`trash/dj/*`)

These classes appear to be part of a deprecated Django application structure.

| Class Name | File | Type |
| :--- | :--- | :--- |
| `BQToolboxConsumer` | `trash/dj/consumers.py` | Consumer |
| `DocumentQueryView` | `trash/dj/views/ask.py` | APIView |
| `BigQRag` | `trash/dj/views/bq_rag.py` | APIView |
| `CreateModelView` | `trash/dj/views/create_model.py` | APIView |
| `GenerateEmbeddingsView` | `trash/dj/views/embed_table.py` | APIView |
| `ProcessDSView` | `trash/dj/views/entry_ds.py` | APIView |
| `BQGetTableDataView` | `trash/dj/views/get_entries.py` | APIView |
| `BQGetTableDataSerializer` | `trash/dj/views/get_entries.py` | Serializer |
| `Gcs2Csv2Bq` | `trash/dj/views/gs2csv2bq.py` | APIView |
| `BQBatchUpsertView` | `trash/dj/views/upsert.py` | APIView |
| `BQBatchUpsertSerializer` | `trash/dj/views/upsert.py` | Serializer |
| `S` | Multiple files in `trash/dj/views/` | Local Serializer aliases |

## Methodology
- Identified all files with `.py` extension in `trash/`.
- Extracted `class` definitions.
- Searched execution codebase (excluding `trash/`) for references to these class names.
- Verified that `SpeechHandler` in `trash` is identical/deprecated vs the active one.
