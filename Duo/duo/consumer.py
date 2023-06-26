import time
from functools import cached_property
from threading import Event, Thread
from typing import Optional

import duo_client
import orjson

from . import LogType
from .iterators import AdminLogsIterator, AuthLogsIterator, OfflineLogsIterator, TelephonyLogsIterator
from .metrics import FORWARD_EVENTS_DURATION, INCOMING_MESSAGES, OUTCOMING_EVENTS


class DuoLogsConsumer(Thread):
    """
    Each endpoint of Duo Admin API is consumed in its own separate thread.
    """

    def __init__(self, connector: "DuoAdminLogsConnector", log_type: LogType, checkpoint: Optional[dict] = None):
        super().__init__()

        self.connector = connector

        self._stop_event = Event()
        self._log_type = log_type

        self.last_checkpoint = checkpoint or {}

        self.frequency = self.connector.configuration.frequency
        self.chunk_size = self.connector.configuration.chunk_size

    def log(self, *args, **kwargs):
        self.connector.log(*args, **kwargs)

    @property
    def log_label(self):
        return self._log_type.name

    def stop(self):
        self._stop_event.set()

    @property
    def running(self):
        return not self._stop_event.is_set()

    @cached_property
    def client(self):
        return duo_client.Admin(
            ikey=self.connector.module.configuration.integration_key,
            skey=self.connector.module.configuration.secret_key,
            host=self.connector.module.configuration.hostname,
        )

    def load_checkpoint(self):
        self.connector.context_lock.acquire()

        with self.connector.context as cache:
            result = cache.get(self._log_type.value, {"min_time": None, "next_offset": None})

        self.connector.context_lock.release()

        return result

    def save_checkpoint(self, **offset):
        key = self._log_type.value

        self.connector.context_lock.acquire()

        with self.connector.context as cache:
            cache[key] = offset

        self.connector.context_lock.release()

    def get_events_iterator(self):
        last_checkpoint = self.load_checkpoint()

        if self._log_type == LogType.ADMINISTRATION:
            min_time = last_checkpoint.get("min_time")

            return AdminLogsIterator(
                client=self.client, min_time=min_time, limit=self.chunk_size, callback=self.save_checkpoint
            )

        elif self._log_type == LogType.AUTHENTICATION:
            min_time = last_checkpoint.get("min_time")
            next_offset = last_checkpoint.get("next_offset")

            return AuthLogsIterator(
                client=self.client,
                min_time=min_time,
                limit=self.chunk_size,
                next_offset=next_offset,
                callback=self.save_checkpoint,
            )

        elif self._log_type == LogType.TELEPHONY:
            min_time = last_checkpoint.get("min_time")
            next_offset = last_checkpoint.get("next_offset")

            return TelephonyLogsIterator(
                client=self.client,
                min_time=min_time,
                limit=self.chunk_size,
                next_offset=next_offset,
                callback=self.save_checkpoint,
            )

        elif self._log_type == LogType.OFFLINE:
            min_time = last_checkpoint.get("min_time")

            return OfflineLogsIterator(
                client=self.client, min_time=min_time, limit=self.chunk_size, callback=self.save_checkpoint
            )

        raise NotImplementedError(f"Unsupported log type {self._log_type}")

    def fetch_batches(self):
        total_num_of_events = 0

        # Fetch next batch
        for events in self.get_events_iterator():
            batch_start_time = time.time()

            # Add `eventtype` field
            for event in events:
                event.update({"eventtype": self._log_type})

            batch_of_events = [orjson.dumps(event).decode("utf-8") for event in events]
            INCOMING_MESSAGES.labels(
                intake_key=self.connector.configuration.intake_key, type=self._log_type.value
            ).inc(len(events))

            # if the batch is full, push it
            if len(batch_of_events) > 0:
                self.connector.push_events_to_intakes(events=batch_of_events)

            total_num_of_events += len(events)

            # get the ending time and compute the duration to fetch the events
            batch_end_time = time.time()
            batch_duration = int(batch_end_time - batch_start_time)
            self.log(
                message=f"Fetched and forwarded {len(batch_of_events)} {self.log_label} events"
                f" in {batch_duration} seconds",
                level="info",
            )

            OUTCOMING_EVENTS.labels(intake_key=self.connector.configuration.intake_key, type=self._log_type.value).inc(
                len(events)
            )

            FORWARD_EVENTS_DURATION.labels(
                intake_key=self.connector.configuration.intake_key, type=self._log_type.value
            ).observe(batch_duration)

            # compute the remaining sleeping time. If greater than 0, sleep
            delta_sleep = self.frequency - batch_duration
            if delta_sleep > 0:
                self.log(
                    message=f"Next batch of {self.log_label} events in the future. " f"Waiting {delta_sleep} seconds",
                    level="info",
                )
                time.sleep(delta_sleep)

        if total_num_of_events == 0:
            time_to_sleep = self.frequency
            self.log(message=f"No new {self.log_label} events. Waiting {time_to_sleep} seconds", level="info")
            time.sleep(time_to_sleep)

    def run(self):
        try:
            while self.running:
                self.fetch_batches()

        except Exception as error:
            self.connector.log_exception(error, message=f"Failed to forward {self.log_label} events")
