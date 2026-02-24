from backend.engine.event_emitter import EventEmitter
from backend.engine.state_manager import StateManager


class Orchestrator:
    def __init__(self, state_manager=None, event_emitter=None):
        self.state_manager = state_manager or StateManager()
        self.event_emitter = event_emitter or EventEmitter()
