class StateManager:
    def __init__(self, initial_state=None):
        self._state = dict(initial_state or {})

    def get(self, key, default=None):
        return self._state.get(key, default)

    def set(self, key, value):
        self._state[key] = value

    def all(self):
        return dict(self._state)
