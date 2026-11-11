from ninja import Router
from esquemas.facturacion import FacturaEmitirRequest, FacturaResponse, PedidoPendienteResponse
from modelos.models import Pedido, Factura
from ninja.errors import HttpError
from rutas.auth import AuthBearer
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
import openpyxl
from io import BytesIO

facturacion_router = Router()

def verificar_admin(request):
    if request.auth.tipo_usuario != "administrador":
        raise HttpError(403, "Se requieren permisos de administrador.")

@facturacion_router.get("/pedidos-pendientes", response=list[PedidoPendienteResponse], auth=AuthBearer())
def listar_pedidos_pendientes(request):
    verificar_admin(request)
    # Mostramos los Completados (listos para facturar) o Pendientes (opcional). 
    # Para la lógica actual, cualquier pedido sin factura
    pedidos_sin_factura = Pedido.objects.filter(facturas__isnull=True).exclude(estado="Cancelado").order_by('-fecha', '-idPedido')
    
    resp = []
    for p in pedidos_sin_factura:
        total = sum([d.subtotal for d in p.detalles.all()])
        # Como los detalles guardan nombre de cliente y el frontend usa responsableRecepcion:
        cliente_nombre = p.responsableRecepcion or (p.detalles.first().cliente if p.detalles.exists() else "Sin Nombre")
        
        resp.append({
            "idPedido": p.idPedido,
            "fecha": p.fecha,
            "cliente": cliente_nombre,
            "estado": p.estado,
            "total": float(total + p.costo_envio)
        })
    return resp

@facturacion_router.post("/emitir", response=FacturaResponse, auth=AuthBearer())
def emitir_factura(request, datos: FacturaEmitirRequest):
    verificar_admin(request)
    with transaction.atomic():
        try:
            pedido = Pedido.objects.get(idPedido=datos.pedido_id)
        except Pedido.DoesNotExist:
            raise HttpError(404, "Pedido no encontrado")
        
        if Factura.objects.filter(pedido=pedido).exists():
            raise HttpError(400, "Este pedido ya ha sido facturado")
        
        subtotal = sum([d.subtotal for d in pedido.detalles.all()]) + pedido.costo_envio
        # iva_porcentaje viene del frontend (ej 19)
        iva_calculado = (subtotal * int(datos.iva_porcentaje)) / 100
        total_pagar = subtotal + iva_calculado
        
        monto_rec = float(datos.monto_recibido or 0)
        cambio = 0
        if datos.metodo_pago.lower() == "efectivo":
            if monto_rec < total_pagar:
                raise HttpError(400, "El monto recibido es menor al total a pagar.")
            cambio = monto_rec - float(total_pagar)
        else:
            monto_rec = float(total_pagar) # Tarjeta o Transferencia exacta
            
        # Generar Consecutivo
        ultimo_id = Factura.objects.all().count() + 1
        num_factura = f"FAC-{ultimo_id:04d}"
        
        factura = Factura.objects.create(
            numero_factura=num_factura,
            nit_cliente=datos.nit_cliente,
            razon_social=datos.razon_social,
            metodo_pago=datos.metodo_pago,
            subtotal=subtotal,
            iva=iva_calculado,
            total=total_pagar,
            monto_recibido=monto_rec,
            cambio=cambio,
            pedido=pedido
        )
        
        pedido.estado = "Pagado"
        pedido.save()
        
        return {
            "idFactura": factura.idFactura,
            "numero_factura": factura.numero_factura,
            "fecha": factura.fecha,
            "nit_cliente": factura.nit_cliente,
            "razon_social": factura.razon_social,
            "metodo_pago": factura.metodo_pago,
            "subtotal": float(factura.subtotal),
            "iva": float(factura.iva),
            "total": float(factura.total),
            "monto_recibido": float(factura.monto_recibido),
            "cambio": float(factura.cambio),
            "pedido_id": pedido.idPedido
        }

@facturacion_router.get("/historial", response=list[FacturaResponse], auth=AuthBearer())
def historial_facturas(request):
    verificar_admin(request)
    facturas = Factura.objects.all().order_by("-idFactura")
    resp = []
    for f in facturas:
        resp.append({
            "idFactura": f.idFactura,
            "numero_factura": f.numero_factura or f"ID-{f.idFactura}",
            "fecha": f.fecha,
            "nit_cliente": f.nit_cliente or "N/A",
            "razon_social": f.razon_social or "N/A",
            "metodo_pago": f.metodo_pago or "N/A",
            "subtotal": float(f.subtotal),
            "iva": float(f.iva),
            "total": float(f.total),
            "monto_recibido": float(f.monto_recibido),
            "cambio": float(f.cambio),
            "pedido_id": f.pedido.idPedido if f.pedido else 0
        })
    return resp

@facturacion_router.get("/exportar-excel", auth=AuthBearer())
def exportar_facturas_excel(request):
    verificar_admin(request)
    
    facturas = Factura.objects.all().order_by("fecha")
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Ventas"
    
    # Encabezados
    headers = ["Consecutivo", "Fecha", "NIT", "Razón Social", "Método Pago", "Subtotal", "IVA", "Total"]
    ws.append(headers)
    
    for f in facturas:
        ws.append([
            f.numero_factura,
            f.fecha.strftime("%Y-%m-%d") if f.fecha else "",
            f.nit_cliente,
            f.razon_social,
            f.metodo_pago,
            float(f.subtotal),
            float(f.iva),
            float(f.total)
        ])
        
    # Ajustar a Bytes
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    response = HttpResponse(stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="Reporte_Ventas_Mensual.xlsx"'
    return response
