import os
import sys

def run_server():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    # Si no se pasan argumentos por la consola, por defecto ejecuta 'runserver'
    args = sys.argv
    if len(args) == 1:
        args = [args[0], "runserver", "127.0.0.1:8000"]
        
    print("Iniciando el servidor de desarrollo de Django para Proyecto Querencia...")
    execute_from_command_line(args)

if __name__ == "__main__":
    run_server()
