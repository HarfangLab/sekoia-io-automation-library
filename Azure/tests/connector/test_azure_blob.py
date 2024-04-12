"""Tests related to connector."""

from datetime import datetime, timedelta, timezone
from gzip import GzipFile
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock

import aiofiles
import pytest
from azure.storage.blob import BlobProperties
from sekoia_automation.module import Module

from connectors.azure_blob import AzureBlobConnector, AzureBlobConnectorConfig


@pytest.fixture
def pushed_events_ids(session_faker) -> list[str]:
    """
    Generate random list of events ids.

    Args:
        session_faker: Faker

    Returns:
        list[str]:
    """
    return [session_faker.word() for _ in range(session_faker.random.randint(1, 10))]


@pytest.fixture
def connector(
    symphony_storage,
    container_name,
    account_name,
    account_key,
    pushed_events_ids,
    mock_push_data_to_intakes,
    session_faker,
):
    module = Module()

    config = AzureBlobConnectorConfig(
        intake_key=session_faker.word(),
        container_name=container_name,
        account_name=account_name,
        account_key=account_key,
    )

    trigger = AzureBlobConnector(
        module=module,
        data_path=symphony_storage,
    )

    # Mock the log function of trigger that requires network access to the api for reporting
    trigger.log = MagicMock()
    trigger.log_exception = MagicMock()

    # Mock the push_events_to_intakes function
    trigger.push_events_to_intakes = MagicMock()
    trigger.push_events_to_intakes.return_value = pushed_events_ids

    trigger.push_data_to_intakes = mock_push_data_to_intakes

    trigger.configuration = config

    return trigger


@pytest.mark.asyncio
async def test_azure_blob_connector_last_event_date(connector):
    """
    Test `last_event_date`.

    Args:
        connector: AzureBlobConnector
    """
    with connector.context as cache:
        cache["last_event_date"] = None

    current_date = datetime.now(timezone.utc).replace(microsecond=0)
    one_hour_ago = current_date - timedelta(hours=1)

    assert connector.last_event_date == one_hour_ago

    with connector.context as cache:
        cache["last_event_date"] = current_date.isoformat()

    assert connector.last_event_date == current_date

    with connector.context as cache:
        cache["last_event_date"] = (one_hour_ago - timedelta(minutes=20)).isoformat()

    assert connector.last_event_date == one_hour_ago


@pytest.mark.asyncio
async def test_azure_blob_get_azure_blob_data_1(
    connector: AzureBlobConnector, session_faker, blob_content, pushed_events_ids
):
    """
    Test AzureBlobConnector get events.

    Args:
        connector: AzureBlobConnector
        session_faker: Faker
        blob_content: bytes
        pushed_events_ids: list[str]
    """
    current_date = datetime.now(timezone.utc).replace(microsecond=0)

    # Try to put last event date higher to be 1 day ahead of the log file date
    with connector.context as cache:
        cache["last_event_date"] = (current_date - timedelta(days=1)).isoformat()

    azure_blob_storage_wrapper = MagicMock()

    properties = BlobProperties()
    properties.last_modified = current_date
    properties.name = session_faker.word()

    expected_blobs = [properties]

    mock_list_blobs = MagicMock()
    mock_list_blobs.__aiter__.return_value = expected_blobs

    azure_blob_storage_wrapper.list_blobs.return_value = mock_list_blobs

    download_blob_result = AsyncMock()
    download_blob_result.return_value = (None, blob_content)

    azure_blob_storage_wrapper.download_blob = download_blob_result

    connector._azure_blob_storage_wrapper = azure_blob_storage_wrapper

    result = await connector.get_azure_blob_data()

    assert result == [blob_content.decode("utf-8")]


@pytest.mark.asyncio
async def test_azure_blob_get_azure_blob_data_2(
    connector: AzureBlobConnector, session_faker, symphony_storage, blob_content, pushed_events_ids
):
    """
    Test AzureBlobConnector get events.

    Args:
        connector: AzureBlobConnector
        session_faker: Faker
        symphony_storage: str
        blob_content: bytes
        pushed_events_ids: list[str]
    """
    current_date = datetime.now(timezone.utc).replace(microsecond=0)

    # Try to put last event date higher to be 1 day ahead of the log file date
    with connector.context as cache:
        cache["last_event_date"] = (current_date - timedelta(days=1)).isoformat()

    async with aiofiles.tempfile.NamedTemporaryFile("wb", delete=False, dir="") as file:
        file_name = str(file.name)
        await file.write(blob_content)

    azure_blob_storage_wrapper = MagicMock()

    properties = BlobProperties()
    properties.last_modified = current_date
    properties.name = session_faker.word()

    expected_blobs = [properties]

    mock_list_blobs = MagicMock()
    mock_list_blobs.__aiter__.return_value = expected_blobs

    azure_blob_storage_wrapper.list_blobs.return_value = mock_list_blobs

    download_blob_result = AsyncMock()
    download_blob_result.return_value = (file_name, None)

    azure_blob_storage_wrapper.download_blob = download_blob_result

    connector._azure_blob_storage_wrapper = azure_blob_storage_wrapper

    result = await connector.get_azure_blob_data()

    assert result == [blob_content.decode("utf-8")]


@pytest.mark.asyncio
async def test_azure_blob_get_azure_blob_data_3(
    connector: AzureBlobConnector, session_faker, symphony_storage, blob_content, pushed_events_ids
):
    """
    Test AzureBlobConnector get events.

    Args:
        connector: AzureBlobConnector
        session_faker: Faker
        symphony_storage: str
        blob_content: bytes
        pushed_events_ids: list[str]
    """
    current_date = datetime.now(timezone.utc).replace(microsecond=0)

    # Try to put last event date higher to be 1 day ahead of the log file date
    with connector.context as cache:
        cache["last_event_date"] = (current_date - timedelta(days=1)).isoformat()

    with NamedTemporaryFile("wb", delete=False, dir="") as file, GzipFile(fileobj=file, mode="w+") as gfile:
        file_name = str(file.name)
        gfile.write(blob_content)

    azure_blob_storage_wrapper = MagicMock()

    properties = BlobProperties()
    properties.last_modified = current_date
    properties.name = session_faker.word()

    expected_blobs = [properties]

    mock_list_blobs = MagicMock()
    mock_list_blobs.__aiter__.return_value = expected_blobs

    azure_blob_storage_wrapper.list_blobs.return_value = mock_list_blobs

    download_blob_result = AsyncMock()
    download_blob_result.return_value = (file_name, None)

    azure_blob_storage_wrapper.download_blob = download_blob_result

    connector._azure_blob_storage_wrapper = azure_blob_storage_wrapper

    result = await connector.get_azure_blob_data()

    assert result == [blob_content.decode("utf-8")]


@pytest.mark.asyncio
async def test_azure_blob_get_azure_blob_data_4(
    connector: AzureBlobConnector, session_faker, symphony_storage, blob_content, pushed_events_ids
):
    """
    Test AzureBlobConnector get events.

    Args:
        connector: AzureBlobConnector
        session_faker: Faker
        symphony_storage: str
        blob_content: bytes
        pushed_events_ids: list[str]
    """
    current_date = datetime.now(timezone.utc).replace(microsecond=0)

    # Try to put last event date higher to be 1 day ahead of the log file date
    with connector.context as cache:
        cache["last_event_date"] = (current_date - timedelta(days=1)).isoformat()

    with NamedTemporaryFile("wb", delete=False, dir="") as file, GzipFile(fileobj=file, mode="w+") as gfile:
        file_name = str(file.name)
        gfile.write(blob_content)
        gfile.write(b"\n")
        gfile.write(b"\n")
        gfile.write(b"\n")
        gfile.write(b"\n")
        gfile.write(b"\n")
        gfile.write(blob_content)
        gfile.write(b"\n")
        gfile.write(blob_content)
        gfile.write(b"\n")

    azure_blob_storage_wrapper = MagicMock()

    properties = BlobProperties()
    properties.last_modified = current_date
    properties.name = session_faker.word()

    expected_blobs = [properties]

    mock_list_blobs = MagicMock()
    mock_list_blobs.__aiter__.return_value = expected_blobs

    azure_blob_storage_wrapper.list_blobs.return_value = mock_list_blobs

    download_blob_result = AsyncMock()
    download_blob_result.return_value = (file_name, None)

    azure_blob_storage_wrapper.download_blob = download_blob_result

    connector._azure_blob_storage_wrapper = azure_blob_storage_wrapper

    result = await connector.get_azure_blob_data()

    assert result == [blob_content.decode("utf-8") for _ in range(3)]


@pytest.mark.asyncio
async def test_azure_blob_get_most_recent_blob(
    connector: AzureBlobConnector, session_faker, symphony_storage, blob_content, pushed_events_ids
):
    """
    Test AzureBlobConnector get events.

    Args:
        connector: AzureBlobConnector
        session_faker: Faker
        symphony_storage: str
        blob_content: bytes
        pushed_events_ids: list[str]
    """
    current_date = datetime.now(timezone.utc).replace(microsecond=0)

    # Try to put last event date higher to be 1 day ahead of the log file date
    with connector.context as cache:
        cache["last_event_date"] = (current_date - timedelta(days=1)).isoformat()

    azure_blob_storage_wrapper = MagicMock()

    properties1 = BlobProperties()
    properties1.last_modified = current_date
    properties1.name = session_faker.word()

    properties2 = BlobProperties()
    properties2.last_modified = current_date + timedelta(minutes=5)
    properties2.name = session_faker.word()

    properties3 = BlobProperties()
    properties3.last_modified = current_date + timedelta(minutes=7)
    properties3.name = session_faker.word()

    expected_blobs = [properties1, properties2, properties3]

    mock_list_blobs = MagicMock()
    mock_list_blobs.__aiter__.return_value = expected_blobs

    azure_blob_storage_wrapper.list_blobs.return_value = mock_list_blobs

    connector._azure_blob_storage_wrapper = azure_blob_storage_wrapper

    blobs_list = [n async for n in connector.get_most_recent_blobs(lower_bound=current_date + timedelta(minutes=2))]

    assert blobs_list == [properties2, properties3]
