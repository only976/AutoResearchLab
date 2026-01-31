import sys
import os
import inspect
from google.adk import Runner

print("Inspecting Runner.__init__:")
try:
    print(inspect.signature(Runner.__init__))
except Exception as e:
    print(e)
