import google.adk
import inspect
import pkgutil

def list_modules(package):
    if hasattr(package, "__path__"):
        for importer, modname, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            print(modname)

print("Listing modules in google.adk:")
list_modules(google.adk)
