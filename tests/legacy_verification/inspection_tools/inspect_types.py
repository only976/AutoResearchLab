import google.adk.types
print(dir(google.adk.types))
try:
    from google.adk.types import Content
    print(Content.model_fields)
except Exception as e:
    print(e)
