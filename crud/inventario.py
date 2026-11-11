from modelos.models import Categoria, Proveedor, Producto, EntradaProducto, RecetaInsumo
from ninja.errors import HttpError
from django.db import transaction
from django.utils import timezone

# --- CATEGORIAS ---
def crear_categoria(datos):
    return Categoria.objects.create(**datos.dict())

# --- PROVEEDORES ---
def crear_proveedor(datos):
    return Proveedor.objects.create(**datos.dict())

# --- PRODUCTOS ---
def crear_producto(datos):
    categoria = None
    if datos.categoria_id:
        categoria = Categoria.objects.get(codigo=datos.categoria_id)
    
    return Producto.objects.create(
        dni_producto=datos.dni_producto,
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        precio=datos.precio,
        stock=datos.stock,
        es_insumo=datos.es_insumo,
        categoria=categoria
    )

def crear_plato_con_insumos(datos):
    with transaction.atomic():
        categoria = None
        if datos.categoria_id:
            categoria = Categoria.objects.get(codigo=datos.categoria_id)

        # 1. Validar insumos y stock disponible
        insumos_a_descontar = []
        if datos.insumos:
            for item in datos.insumos:
                cant = int(item.cantidad)
                if cant <= 0:
                    continue
                try:
                    insumo = Producto.objects.select_for_update().get(dni_producto=item.producto_id, es_insumo=True)
                except Producto.DoesNotExist:
                    raise HttpError(404, f"El insumo con código '{item.producto_id}' no existe en el inventario.")
                
                if insumo.stock < cant:
                    raise HttpError(
                        400,
                        f"Stock insuficiente para '{insumo.nombre}'. Disponible: {insumo.stock}, solicitado: {cant}."
                    )
                insumos_a_descontar.append((insumo, cant))

        # 2. Descontar el stock de cada insumo
        for insumo, cant in insumos_a_descontar:
            insumo.stock -= cant
            insumo.save()

        # 3. Crear el plato en el menú
        plato = Producto.objects.create(
            dni_producto=datos.dni_producto,
            nombre=datos.nombre.strip(),
            descripcion=datos.descripcion or '',
            precio=datos.precio,
            stock=datos.stock,
            es_insumo=False,
            categoria=categoria
        )

        # 4. Guardar los ingredientes en RecetaInsumo
        for insumo, cant in insumos_a_descontar:
            RecetaInsumo.objects.create(
                plato=plato,
                insumo=insumo,
                cantidad=cant
            )

        return plato

def actualizar_producto(id_producto, datos):
    with transaction.atomic():
        producto = Producto.objects.select_for_update().get(dni_producto=id_producto)
        datos_dict = datos.dict(exclude_unset=True)

        # Si se especificaron insumos para la receta del plato
        if 'insumos' in datos_dict:
            nuevos_insumos = datos_dict.pop('insumos')
            if nuevos_insumos is not None:
                # 1. Devolver el stock de los insumos anteriores
                for rec in producto.ingredientes_receta.select_for_update().all():
                    rec.insumo.stock += rec.cantidad
                    rec.insumo.save()

                producto.ingredientes_receta.all().delete()

                # 2. Validar y descontar stock para los nuevos insumos
                insumos_a_descontar = []
                for item in nuevos_insumos:
                    cant = int(item['cantidad'] if isinstance(item, dict) else item.cantidad)
                    prod_id = str(item['producto_id'] if isinstance(item, dict) else item.producto_id)
                    if cant <= 0:
                        continue
                    try:
                        insumo = Producto.objects.select_for_update().get(dni_producto=prod_id, es_insumo=True)
                    except Producto.DoesNotExist:
                        raise HttpError(404, f"Insumo con código '{prod_id}' no encontrado.")

                    if insumo.stock < cant:
                        raise HttpError(
                            400,
                            f"Stock insuficiente para '{insumo.nombre}'. Disponible: {insumo.stock}, solicitado: {cant}."
                        )
                    insumos_a_descontar.append((insumo, cant))

                for insumo, cant in insumos_a_descontar:
                    insumo.stock -= cant
                    insumo.save()
                    RecetaInsumo.objects.create(
                        plato=producto,
                        insumo=insumo,
                        cantidad=cant
                    )

        # Actualizar atributos regulares
        for attr, value in datos_dict.items():
            if attr == "categoria_id":
                if value:
                    producto.categoria = Categoria.objects.get(codigo=value)
                else:
                    producto.categoria = None
            else:
                setattr(producto, attr, value)

        producto.save()
        return producto

def formatear_producto(producto):
    ingredientes = []
    if not producto.es_insumo:
        try:
            for rec in producto.ingredientes_receta.select_related('insumo').all():
                ingredientes.append({
                    "producto_id": str(rec.insumo.dni_producto),
                    "nombre": rec.insumo.nombre,
                    "cantidad": rec.cantidad
                })
        except Exception:
            pass

    return {
        "dni_producto": str(producto.dni_producto),
        "idProducto": str(producto.dni_producto),
        "nombre": producto.nombre,
        "descripcion": producto.descripcion or "",
        "precio": float(producto.precio),
        "stock": producto.stock,
        "es_insumo": producto.es_insumo,
        "categoria_id": producto.categoria.codigo if producto.categoria else None,
        "categoria_nombre": producto.categoria.nombre if producto.categoria else None,
        "ingredientes": ingredientes
    }

# --- ENTRADAS ---
def registrar_entrada(datos):
    with transaction.atomic():
        producto = Producto.objects.get(dni_producto=datos.producto_id)
        proveedor = Proveedor.objects.get(nit=datos.proveedor_id)
        
        costo_total = datos.cantidad * datos.precio_compra_unidad
        
        # Crear la entrada
        entrada = EntradaProducto.objects.create(
            cantidad=datos.cantidad,
            precio_compra_unidad=datos.precio_compra_unidad,
            costo_total=costo_total,
            fechaEntrada=timezone.now().date(),
            proveedor=proveedor,
            producto=producto
        )
        
        # Actualizar el stock sumando la nueva cantidad
        producto.stock += datos.cantidad
        producto.save()
        
        return entrada

def formatear_entrada(entrada):
    return {
        "idEntrada": entrada.idEntrada,
        "cantidad": entrada.cantidad,
        "precio_compra_unidad": float(entrada.precio_compra_unidad),
        "costo_total": float(entrada.costo_total),
        "fechaEntrada": entrada.fechaEntrada,
        "proveedor_id": entrada.proveedor.nit,
        "proveedor_nombre": entrada.proveedor.nombre,
        "producto_id": entrada.producto.dni_producto,
        "producto_nombre": entrada.producto.nombre
    }
