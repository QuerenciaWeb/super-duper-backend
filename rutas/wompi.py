import json
from ninja import Router
from django.http import HttpResponse, HttpRequest

from core.wompi_utils import validar_firma_webhook
from modelos.models import Pedido

wompi_router = Router()

@wompi_router.post("/webhook")
def wompi_webhook(request: HttpRequest):
    """
    Recibe los eventos asíncronos de Wompi. No usa AuthBearer porque Wompi envía
    la petición y valida su identidad mediante la firma criptográfica.
    """
    try:
        body = json.loads(request.body)
        
        # Obtener los datos para validar
        signature = body.get('signature', {})
        properties = signature.get('properties', [])
        checksum = signature.get('checksum', '')
        timestamp = body.get('timestamp', '')
        
        # Si no hay firma, no lo podemos validar
        if not properties or not checksum:
            return HttpResponse("Firma incompleta", status=400)
            
        # Validar
        es_valido = validar_firma_webhook(properties, checksum, int(timestamp), body)
        if not es_valido:
            # Aunque sea inválido, respondemos 200 en produccion para evitar reintentos de ataques,
            # pero aquí mandamos 400 para depurar fácilmente.
            return HttpResponse("Firma no válida", status=400)
            
        # Extraer el evento y la info
        event_type = body.get('event')
        data = body.get('data', {}).get('transaction', {})
        
        if event_type == "transaction.updated":
            estado_transaccion = data.get('status')
            referencia = data.get('reference')
            
            # Buscar el pedido
            try:
                pedido = Pedido.objects.get(wompi_transaction_id=referencia)
                if estado_transaccion == "APPROVED":
                    pedido.estado = "Pagado"
                elif estado_transaccion in ["DECLINED", "ERROR", "VOIDED"]:
                    # No cancelamos el pedido entero, solo el pago
                    pedido.estado = "Error Pago"
                pedido.save()
            except Pedido.DoesNotExist:
                # Transacción no es de un pedido (o se borró)
                pass
                
        # IMPORTANTE: Wompi requiere un 200 OK para saber que recibimos el webhook
        return HttpResponse("OK", status=200)
        
    except json.JSONDecodeError:
        return HttpResponse("Body no es JSON", status=400)
    except Exception as e:
        print(f"Error en webhook Wompi: {e}")
        return HttpResponse("Error interno", status=500)
