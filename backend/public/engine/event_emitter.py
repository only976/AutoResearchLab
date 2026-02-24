class EventEmitter:
    def __init__(self):
        self._listeners = {}

    def on(self, event_name, handler):
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(handler)

    def emit(self, event_name, payload=None):
        for handler in self._listeners.get(event_name, []):
            handler(payload)
