from typing import Callable, Optional

import duo_client


class DuoV1LogsIterator:
    def __init__(self, func: Callable, min_time: int = 0, limit: int = 1000, callback: Optional[Callable] = None):
        self.min_time = min_time if min_time else 0
        self.func = func
        self.limit = limit
        self.callback = callback

    def __iter__(self):
        return self

    def __next__(self):
        events = self.func(mintime=self.min_time)
        events = sorted(events, key=lambda e: e["timestamp"])
        events = events[: self.limit]

        if len(events) > 0:
            self.min_time = events[-1]["timestamp"] + 1

            if self.callback:
                self.callback(min_time=self.min_time)

        else:
            raise StopIteration

        return events


class DuoV2LogsIterator:
    ITEMS_FIELD = ""

    def __init__(self, func: Callable, **kwargs):
        self.func = func

        self.callback = kwargs.get("callback")
        self.min_time = kwargs.get("min_time")
        self.next_offset = kwargs.get("next_offset")
        self.limit = kwargs.get("limit", 1000)

    def __iter__(self):
        return self

    def __next__(self):
        if self.next_offset:
            response = self.func(next_offset=self.next_offset, api_version=2, limit=str(self.limit), sort="ts:asc")

        else:
            response = self.func(mintime=self.min_time, api_version=2, limit=str(self.limit), sort="ts:asc")

        events = response.get(self.ITEMS_FIELD)
        response_metadata = response.get("metadata", {})

        next_offset = response_metadata.get("next_offset")
        if next_offset:
            self.next_offset = next_offset

            if self.callback:
                self.callback(next_offset=self.next_offset)

        if len(events) == 0:
            raise StopIteration

        return events


class AdminLogsIterator(DuoV1LogsIterator):
    def __init__(self, client: duo_client.Admin, min_time: int, limit: int = 1000, callback: Callable = None):
        super().__init__(func=client.get_administrator_log, min_time=min_time, limit=limit, callback=callback)


class TelephonyLogsIterator(DuoV2LogsIterator):
    ITEMS_FIELD = "items"

    def __init__(self, client: duo_client.Admin, **kwargs):
        super().__init__(func=client.get_telephony_log, **kwargs)


class AuthLogsIterator(DuoV2LogsIterator):
    ITEMS_FIELD = "authlogs"

    def __init__(self, client: duo_client.Admin, **kwargs):
        super().__init__(func=client.get_authentication_log, **kwargs)


class OfflineLogsIterator(DuoV1LogsIterator):
    def __init__(self, client: duo_client.Admin, min_time: int, limit: int = 1000, callback: Callable = None):
        super().__init__(func=client.get_offline_log, min_time=min_time, limit=limit, callback=callback)
