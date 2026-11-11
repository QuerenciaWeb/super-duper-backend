from ninja import Router
from typing import List
from django.utils import timezone
from datetime import timedelta
from ninja.errors import HttpError
from django.http import HttpResponse

from rutas.auth import AuthBearer
from modelos.models import Producto, Pedido, Factura
from esquemas.caja import (
    ProductoResponse, PedidoCreate, PedidoUpdate, 
    PedidoResponse, FacturaResponse
)
from crud.caja import (
    crear_pedido_crud, formatear_pedido_response, 
    enviar_pedido_proveedor, generar_factura_pedido,
    generar_pdf_factura
)

caja_router = Router()

@caja_router.get("/productos", response=List[ProductoResponse], auth=AuthBearer())
def listar_productos(request):
    return Producto.objects.filter(es_insumo=False)

@caja_router.post("/pedidos", response=PedidoResponse, auth=AuthBearer())
def crear_pedido(request, datos: PedidoCreate):
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "Solo administradores pueden crear pedidos")
    
    try:
        nuevo_pedido = crear_pedido_crud(datos, request.auth)
        return formatear_pedido_response(nuevo_pedido)
    except ValueError as e:
        raise HttpError(400, str(e))

import requests
import os
import re
import urllib.parse
from esquemas.caja import CalcularEnvioRequest

from crud.caja import (
    crear_pedido_crud, actualizar_pedido_crud, formatear_pedido_response, 
    enviar_pedido_proveedor, generar_factura_pedido,
    generar_pdf_factura
)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
# IMPORTANTE: Cambia esta variable por la dirección real de tu local para que el cálculo sea exacto
DIRECCION_ORIGEN = os.getenv("DIRECCION_ORIGEN", "Cali, Valle del Cauca, Colombia")

def geocodificar_osm(direccion: str):
    """Intenta geocodificar una dirección usando OpenStreetMap Nominatim"""
    clean_dir = direccion.replace('#', ' ').replace('-', ' ').replace('No.', ' ').replace('N°', ' ')
    headers = {'User-Agent': 'QuerenciaApp/1.0 (contacto@laquerencia.com)'}
    try:
        res = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': clean_dir, 'format': 'json', 'limit': 1},
            headers=headers,
            timeout=4
        )
        if res.ok:
            data = res.json()
            if data and len(data) > 0:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
    return None

def calcular_distancia_osrm(lat1: float, lon1: float, lat2: float, lon2: float):
    """Calcula distancia real por carretera usando el motor OSRM"""
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
        res = requests.get(url, timeout=5)
        if res.ok:
            data = res.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                metros = data['routes'][0]['distance']
                return metros / 1000.0
    except Exception:
        pass
    # Fallback por fórmula de Haversine si OSRM no responde
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return (R * c) * 1.3

@caja_router.post("/calcular-envio", auth=AuthBearer())
def calcular_envio(request, body: CalcularEnvioRequest):
    direccion_destino = body.direccion.strip()
    if not direccion_destino:
        return {"distancia_km": 0.0, "costo_envio": 0.0, "mapa_url": ""}

    direccion_origen = (body.origen or "").strip() or DIRECCION_ORIGEN

    # Asegurar sufijo de contexto colombiano si no lo tiene
    dir_dest_query = direccion_destino
    if "colombia" not in dir_dest_query.lower():
        dir_dest_query += ", Cali, Valle del Cauca, Colombia"

    dir_orig_query = direccion_origen
    if "colombia" not in dir_orig_query.lower():
        dir_orig_query += ", Cali, Valle del Cauca, Colombia"

    dir_codificada = urllib.parse.quote(dir_dest_query)
    mapa_url = f"https://www.google.com/maps/search/?api=1&query={dir_codificada}"

    km_calculados = None

    # TIER 1: Intento con Google Maps si hay una clave válida configurada
    if GOOGLE_MAPS_API_KEY and len(GOOGLE_MAPS_API_KEY) > 10:
        try:
            url_gmaps = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": dir_orig_query,
                "destinations": dir_dest_query,
                "key": GOOGLE_MAPS_API_KEY,
                "units": "metric"
            }
            res_g = requests.get(url_gmaps, params=params, timeout=4)
            data_g = res_g.json()
            if data_g.get("status") == "OK":
                element = data_g["rows"][0]["elements"][0]
                if element.get("status") == "OK":
                    metros = element["distance"]["value"]
                    km_calculados = metros / 1000.0
                    mapa_url = f"https://maps.googleapis.com/maps/api/staticmap?center={dir_codificada}&zoom=15&size=200x200&markers=color:red%7C{dir_codificada}&key={GOOGLE_MAPS_API_KEY}"
        except Exception:
            pass

    # TIER 2: Intento con OpenStreetMap (Nominatim + OSRM)
    if km_calculados is None:
        coords_dest = geocodificar_osm(dir_dest_query)
        coords_orig = geocodificar_osm(dir_orig_query)

        # Si el origen no se resolvió, usar coordenadas centrales de Cali (3.4516, -76.5320)
        if not coords_orig:
            coords_orig = (3.4516, -76.5320)

        if coords_dest and coords_orig:
            km_osrm = calcular_distancia_osrm(coords_orig[0], coords_orig[1], coords_dest[0], coords_dest[1])
            if km_osrm and km_osrm > 0:
                km_calculados = km_osrm

    # TIER 3: Heurística urbana para direcciones locales (cuadras / nomenclatura)
    if km_calculados is None or km_calculados <= 0:
        nums = [int(n) for n in re.findall(r'\b\d+\b', direccion_destino) if int(n) < 150]
        if len(nums) >= 2:
            cuadras = abs(nums[0] - 10) + abs(nums[1] - 5)
            km_calculados = max(1.5, min(14.0, cuadras * 0.11))
        elif len(nums) == 1:
            km_calculados = max(1.8, min(10.0, nums[0] * 0.15))
        else:
            km_calculados = 3.5

    km_redondeado = round(km_calculados, 1)
    costo = 3000 + (1000 * int(km_redondeado))

    return {
        "distancia_km": km_redondeado,
        "costo_envio": float(costo),
        "mapa_url": mapa_url
    }

@caja_router.get("/pedidos", response=List[PedidoResponse], auth=AuthBearer())
def listar_pedidos(request):
    pedidos = Pedido.objects.all().order_by('-fecha', '-idPedido')
    return [formatear_pedido_response(p) for p in pedidos]

@caja_router.put("/pedidos/{pedido_id}", response=PedidoResponse, auth=AuthBearer())
def actualizar_pedido(request, pedido_id: int, datos: PedidoUpdate):
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "Solo administradores pueden modificar pedidos")
        
    try:
        pedido = actualizar_pedido_crud(pedido_id, datos)
        return formatear_pedido_response(pedido)
    except HttpError:
        raise
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Error actualizando pedido: {str(e)}")

@caja_router.delete("/pedidos/{pedido_id}", auth=AuthBearer())
def cancelar_pedido(request, pedido_id: int):
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "Solo administradores")
        
    try:
        pedido = Pedido.objects.get(idPedido=pedido_id)
        # Devolver el stock
        for det in pedido.detalles.all():
            det.producto.stock += det.cantidad
            det.producto.save()
            
        pedido.estado = "Cancelado"
        pedido.save()
        return {"message": "Pedido cancelado correctamente y stock devuelto."}
    except Pedido.DoesNotExist:
        raise HttpError(404, "Pedido no encontrado")

@caja_router.post("/pedidos/{pedido_id}/enviar-proveedor", auth=AuthBearer())
def enviar_a_proveedor(request, pedido_id: int):
    exito = enviar_pedido_proveedor(pedido_id)
    if exito:
        return {"message": "Pedido enviado al proveedor"}
    raise HttpError(500, "Error enviando correo")

@caja_router.put("/pedidos/{pedido_id}/recepcion", auth=AuthBearer())
def verificar_recepcion(request, pedido_id: int):
    try:
        pedido = Pedido.objects.get(idPedido=pedido_id)
        pedido.estado = "Recibido"
        pedido.save()
        return {"message": "Pedido marcado como recibido"}
    except Pedido.DoesNotExist:
        raise HttpError(404, "Pedido no encontrado")

@caja_router.post("/pedidos/{pedido_id}/factura", response=FacturaResponse, auth=AuthBearer())
def generar_factura(request, pedido_id: int):
    try:
        pedido = Pedido.objects.get(idPedido=pedido_id)
        if pedido.estado not in ["Completado", "Pagado"]:
            raise HttpError(400, "El pedido debe estar pagado para poder generar la factura.")
            
        factura = generar_factura_pedido(pedido_id)
        
        # ACTULIZAR ESTADO A COMPLETADO
        if pedido.estado != "Completado":
            pedido.estado = "Completado"
            pedido.save()
            
        return factura
    except Pedido.DoesNotExist:
        raise HttpError(404, "Pedido no encontrado")

@caja_router.get("/pedidos/{pedido_id}/pdf", auth=AuthBearer())
def descargar_pdf_por_pedido(request, pedido_id: int):
    try:
        pedido = Pedido.objects.get(idPedido=pedido_id)
        factura = pedido.facturas.first()
        if not factura:
            raise HttpError(404, "El pedido aún no tiene factura generada")
            
        buffer = generar_pdf_factura(factura.idFactura)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="factura_pedido_{pedido_id}.pdf"'
        return response
    except Pedido.DoesNotExist:
        raise HttpError(404, "Pedido no encontrado")

@caja_router.get("/reporte-ventas", auth=AuthBearer())
def reporte_ventas(request):
    fecha_inicio = timezone.now().date() - timedelta(days=30)
    facturas = Factura.objects.filter(fecha__gte=fecha_inicio)
    
    total_ventas = sum(f.total for f in facturas)
    return {
        "dias": 30,
        "cantidad_facturas": facturas.count(),
        "total_ventas": total_ventas,
        "facturas": [{"id": f.idFactura, "fecha": f.fecha, "total": f.total, "pedido_id": f.pedido.idPedido} for f in facturas]
    }
