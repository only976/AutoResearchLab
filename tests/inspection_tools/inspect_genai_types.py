from google.genai import types
import inspect

print("Content init:")
try:
    print(inspect.signature(types.Content.__init__))
except:
    print("Could not get signature")

print("\nContent fields:")
try:
    print(types.Content.model_fields)
except:
    print(dir(types.Content))
