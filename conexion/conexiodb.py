from django.db import connection, connections
from django.db.utils import OperationalError

def verificar_conexion():
    """
    Verifica si la conexión a la base de datos PostgreSQL configurada
    en Django (settings.py) está activa y responde.
    """
    try:
        # Intentar establecer conexión y ejecutar una consulta simple
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        return True, "Conexión a PostgreSQL establecida correctamente."
    except OperationalError as e:
        return False, f"Fallo al conectar a PostgreSQL: {e}"

def obtener_cursor():
    """
    Retorna un cursor para ejecutar consultas SQL puras si es necesario,
    utilizando el pool de conexiones de Django.
    """
    return connection.cursor()
