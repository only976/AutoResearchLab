from google.genai import types
import inspect

print("Part fields:")
try:
    print(types.Part.model_fields)
except:
    print(dir(types.Part))
