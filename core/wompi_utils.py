import hashlib
import hmac
import os

WOMPI_PUB_KEY = os.getenv("WOMPI_PUB_KEY", "pub_prod_lUAvrkESbSsrCVTSNYqP5AdpYfPRnET7")
WOMPI_PRV_KEY = os.getenv("WOMPI_PRV_KEY", "prv_prod_X0zDA9xoKdePzhX8le4WTYig16V") # Placeholder privado
WOMPI_EVENTS_SECRET = os.getenv("WOMPI_EVENTS_SECRET", "prod_events_j82k3k21") # Placeholder eventos
WOMPI_INTEGRITY_KEY = os.getenv("WOMPI_INTEGRITY_KEY", "prod_integrity_LXURyPaY95vLBpbh3XBNef9L7F8luOVz")

def validar_firma_webhook(signature_properties: list, signature_checksum: str, timestamp: int, event_body: dict) -> bool:
    """
    Valida la firma HMAC SHA256 de un evento (webhook) de Wompi.
    Concatena los valores de signature.properties, el timestamp y el EVENT_SECRET.
    """
    try:
        # Extraer los valores en orden exacto
        cadena = ""
        for prop in signature_properties:
            # Dividir propiedades anidadas como 'transaction.id'
            keys = prop.split('.')
            val = event_body
            for k in keys:
                val = val.get(k)
                if val is None:
                    break
            
            # Formatear números para evitar problemas (ej. centavos a entero)
            if isinstance(val, float) and val.is_integer():
                val = int(val)
                
            cadena += str(val) if val is not None else ""
        
        # Agregar timestamp y el EVENT_SECRET
        cadena += str(timestamp) + WOMPI_EVENTS_SECRET
        
        # Calcular el SHA256
        hash_calculado = hashlib.sha256(cadena.encode('utf-8')).hexdigest()
        
        return hash_calculado == signature_checksum
    except Exception as e:
        print(f"Error validando firma Wompi: {e}")
        return False

def generar_firma_integridad(referencia: str, monto_centavos: int, moneda: str = "COP") -> str:
    """
    Genera la firma de integridad para enviar en la creación de transacciones / widget checkout.
    Concatenación: <referencia><monto_en_centavos><moneda><llave_de_integridad>
    """
    cadena = f"{referencia}{monto_centavos}{moneda}{WOMPI_INTEGRITY_KEY}"
    return hashlib.sha256(cadena.encode('utf-8')).hexdigest()
