import os
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.http import Http404

from modelos.models import Producto, Pedido, DetallePedido, Factura, Facturacion, Categoria
from esquemas.caja import PedidoCreate, PedidoUpdate
from core.wompi_utils import generar_firma_integridad, WOMPI_PUB_KEY

def crear_pedido_crud(datos: PedidoCreate, usuario):
    with transaction.atomic():
        nuevo_pedido = Pedido.objects.create(
            fecha=timezone.now().date(),
            estado="Pendiente",
            responsableRecepcion=datos.responsableRecepcion,
            direccionEnvio=datos.direccionEnvio,
            distancia_km=datos.distancia_km or 0.0,
            costo_envio=datos.costo_envio or 0,
            usuario=usuario
        )
        
        total_pedido = float(datos.costo_envio or 0)
        for det in datos.detalles:
            try:
                producto = Producto.objects.get(dni_producto=det.producto_id)
            except Producto.DoesNotExist:
                raise ValueError(f"Producto con ID {det.producto_id} no existe.")
            
            subtotal = producto.precio * det.cantidad
            total_pedido += float(subtotal)
            
            # Reducir stock
            if producto.stock >= det.cantidad:
                producto.stock -= det.cantidad
                producto.save()
            else:
                raise ValueError(f"Stock insuficiente para {producto.nombre}.")
                
            DetallePedido.objects.create(
                cantidad=det.cantidad,
                subtotal=subtotal,
                cliente=datos.cliente,
                cedulaCliente=datos.cedulaCliente,
                pedido=nuevo_pedido,
                producto=producto
            )
            
        # Generar firma para el widget Wompi (monto en centavos)
        monto_centavos = int(total_pedido * 100)
        referencia = f"PEDIDO-{nuevo_pedido.idPedido}-{int(timezone.now().timestamp())}"
        firma = generar_firma_integridad(referencia, monto_centavos)
        
        # Guardar info básica en el pedido para pasarela
        url_checkout = f"https://checkout.wompi.co/p/?public-key={WOMPI_PUB_KEY}&currency=COP&amount-in-cents={monto_centavos}&reference={referencia}&signature:integrity={firma}"
        
        nuevo_pedido.wompi_payment_url = url_checkout
        nuevo_pedido.wompi_transaction_id = referencia # Usaremos esto para validar en el webhook
        nuevo_pedido.save()

        return nuevo_pedido

def actualizar_pedido_crud(pedido_id: int, datos: PedidoUpdate):
    with transaction.atomic():
        try:
            pedido = Pedido.objects.select_for_update().get(idPedido=pedido_id)
        except Pedido.DoesNotExist:
            raise Http404("Pedido no encontrado")
            
        estado_previo = pedido.estado

        # Actualizar campos de cabecera si vienen especificados
        if datos.responsableRecepcion is not None:
            pedido.responsableRecepcion = datos.responsableRecepcion.strip()
        if datos.direccionEnvio is not None:
            pedido.direccionEnvio = datos.direccionEnvio.strip()
        if datos.distancia_km is not None:
            pedido.distancia_km = float(datos.distancia_km)
        if datos.costo_envio is not None:
            pedido.costo_envio = float(datos.costo_envio)
        if datos.estado is not None:
            nuevo_estado = datos.estado.strip()
            if nuevo_estado == "Cancelado" and estado_previo != "Cancelado" and datos.detalles is None:
                for d in pedido.detalles.all():
                    d.producto.stock += d.cantidad
                    d.producto.save()
            pedido.estado = nuevo_estado

        # Determinar nombre y cédula del cliente
        cliente_actual = datos.cliente
        if not cliente_actual:
            primer_det = pedido.detalles.first()
            cliente_actual = primer_det.cliente if primer_det else "Cliente General"

        cedula_actual = datos.cedulaCliente
        if not cedula_actual:
            primer_det = pedido.detalles.first()
            cedula_actual = primer_det.cedulaCliente if primer_det else 0

        # Si no se cambiaron los detalles de productos, actualizar cliente y cédula en los detalles existentes
        if datos.detalles is None:
            if datos.cliente is not None or datos.cedulaCliente is not None:
                for d in pedido.detalles.all():
                    if datos.cliente is not None:
                        d.cliente = cliente_actual
                    if datos.cedulaCliente is not None:
                        d.cedulaCliente = cedula_actual
                    d.save()
        else:
            # Se proporcionaron nuevos detalles de productos
            # 1. Revertir el stock de los productos anteriores si el pedido no estaba cancelado
            if estado_previo != "Cancelado":
                for d in pedido.detalles.all():
                    d.producto.stock += d.cantidad
                    d.producto.save()

            # Eliminar detalles previos
            pedido.detalles.all().delete()

            # 2. Validar y descontar stock para los nuevos productos (si el nuevo estado no es Cancelado)
            for det in datos.detalles:
                try:
                    producto = Producto.objects.select_for_update().get(dni_producto=det.producto_id)
                except Producto.DoesNotExist:
                    raise ValueError(f"El producto con ID {det.producto_id} no existe.")

                if pedido.estado != "Cancelado":
                    if producto.stock < det.cantidad:
                        raise ValueError(f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock}, Solicitado: {det.cantidad}")
                    producto.stock -= det.cantidad
                    producto.save()

                subtotal = producto.precio * det.cantidad
                DetallePedido.objects.create(
                    pedido=pedido,
                    producto=producto,
                    cantidad=det.cantidad,
                    subtotal=subtotal,
                    cliente=cliente_actual,
                    cedulaCliente=cedula_actual
                )

        # Recalcular el total general y regenerar el enlace Wompi
        total_items = sum(float(d.subtotal) for d in pedido.detalles.all())
        total_pedido = total_items + float(pedido.costo_envio or 0)

        monto_centavos = int(total_pedido * 100)
        referencia = f"PEDIDO-{pedido.idPedido}-{int(timezone.now().timestamp())}"
        firma = generar_firma_integridad(referencia, monto_centavos)
        url_checkout = f"https://checkout.wompi.co/p/?public-key={WOMPI_PUB_KEY}&currency=COP&amount-in-cents={monto_centavos}&reference={referencia}&signature:integrity={firma}"
        pedido.wompi_payment_url = url_checkout
        pedido.wompi_transaction_id = referencia
        pedido.save()

        return pedido

def formatear_pedido_response(pedido):
    detalles = []
    total = 0
    for d in pedido.detalles.all():
        detalles.append({
            "idDetalle": d.idDetalle,
            "producto_id": d.producto.dni_producto,
            "producto_nombre": d.producto.nombre,
            "cantidad": d.cantidad,
            "subtotal": float(d.subtotal),
            "cliente": d.cliente,
            "cedulaCliente": d.cedulaCliente
        })
        total += float(d.subtotal)
        
    return {
        "idPedido": pedido.idPedido,
        "fecha": pedido.fecha,
        "estado": pedido.estado,
        "responsableRecepcion": pedido.responsableRecepcion,
        "direccionEnvio": pedido.direccionEnvio,
        "distancia_km": pedido.distancia_km,
        "costo_envio": float(pedido.costo_envio),
        "usuario_id": pedido.usuario.dni,
        "total": total + float(pedido.costo_envio),
        "detalles": detalles,
        "wompi_transaction_id": pedido.wompi_transaction_id,
        "wompi_payment_url": pedido.wompi_payment_url
    }

def enviar_pedido_proveedor(pedido_id: int):
    pedido = Pedido.objects.get(idPedido=pedido_id)
    # Simulación de correo al proveedor
    detalles = pedido.detalles.all()
    lista_items = "\\n".join([f"- {d.cantidad}x {d.producto.nombre}" for d in detalles])
    
    mensaje = f"Estimado Proveedor,\\n\\nSe solicita el siguiente pedido (#{pedido.idPedido}):\\n{lista_items}\\n\\nResponsable de Recepción: {pedido.responsableRecepcion}\\n\\nGracias."
    try:
        send_mail(
            subject=f"Nuevo Pedido #{pedido.idPedido} - La Querencia",
            message=mensaje,
            from_email="admin@laquerencia.com",
            recipient_list=["proveedor@ejemplo.com"],
            fail_silently=True
        )
        pedido.estado = "En Proceso"
        pedido.save()
        return True
    except Exception as e:
        return False

def generar_factura_pedido(pedido_id: int):
    with transaction.atomic():
        pedido = Pedido.objects.get(idPedido=pedido_id)
        if hasattr(pedido, 'facturas') and pedido.facturas.exists():
            return pedido.facturas.first() # Ya tiene factura
            
        total = sum(d.subtotal for d in pedido.detalles.all())
        factura = Factura.objects.create(
            fecha=timezone.now().date(),
            total=total,
            pedido=pedido
        )
        # Crear la facturación para la caja
        Facturacion.objects.create(
            tipo="Venta (Pedido Completado)",
            monto=total,
            pedido=pedido,
            fecha=timezone.now().date(),
            factura=factura
        )
        return factura

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

def generar_pdf_factura(factura_id: int):
    factura = Factura.objects.get(idFactura=factura_id)
    pedido = factura.pedido
    detalles = pedido.detalles.all()
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Encabezado
    p.setFont("Helvetica-Bold", 18)
    p.drawString(100, 750, "La Querencia - Factura de Venta")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 720, f"Factura #{factura.idFactura}")
    p.drawString(100, 700, f"Fecha: {factura.fecha.strftime('%d/%m/%Y')}")
    p.drawString(100, 680, f"Pedido Asociado: #{pedido.idPedido}")
    
    # Cliente
    cliente = detalles[0].cliente if detalles.exists() else "Consumidor Final"
    cedula = detalles[0].cedulaCliente if detalles.exists() else ""
    p.drawString(100, 650, f"Cliente: {cliente} (C.C. {cedula})")
    
    # Detalles
    p.drawString(100, 610, "Cant.")
    p.drawString(150, 610, "Producto")
    p.drawString(350, 610, "V. Unit")
    p.drawString(450, 610, "Subtotal")
    p.line(100, 605, 500, 605)
    
    y = 580
    for d in detalles:
        v_unit = float(d.producto.precio)
        p.drawString(100, y, str(d.cantidad))
        p.drawString(150, y, d.producto.nombre)
        p.drawString(350, y, f"${v_unit:,.2f}")
        p.drawString(450, y, f"${d.subtotal:,.2f}")
        y -= 20
        
    p.line(100, y, 500, y)
    y -= 20
    p.setFont("Helvetica-Bold", 14)
    p.drawString(350, y, "Total:")
    p.drawString(450, y, f"${factura.total:,.2f}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer
