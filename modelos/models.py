import uuid
from django.db import models
from django.core.mail import send_mail


# ============================================================
# Modelo existente: TokenInvitacion (se conserva sin cambios)
# ============================================================
class TokenInvitacion(models.Model):
    correo_destino = models.EmailField(max_length=100)
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    tipo_usuario = models.CharField(max_length=20, default='normal') # 'administrador' | 'normal'
    usado = models.BooleanField(default=False)
    fecha_expiracion = models.DateTimeField()

    class Meta:
        db_table = 'tokens_invitacion'
        verbose_name = 'Token de Invitación'
        verbose_name_plural = 'Tokens de Invitación'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.token:
            self.token = str(uuid.uuid4())
        super().save(*args, **kwargs)
        if is_new:
            try:
                subject = "Nuevo Token de Invitación Generado - La Querencia"
                message = (
                    f"Hola Administrador,\n\n"
                    f"Se ha generado un nuevo token de invitación en el sistema La Querencia:\n\n"
                    f"Correo de destino: {self.correo_destino}\n"
                    f"Rol asignado: {self.tipo_usuario}\n"
                    f"Token: {self.token}\n"
                    f"Fecha de expiración: {self.fecha_expiracion}\n\n"
                    f"Copia este código y entrégalo al usuario para que complete su registro.\n\n"
                    f"Saludos,\nSistemas La Querencia"
                )
                send_mail(
                    subject=subject,
                    message=message,
                    from_email="noreply@laquerencia.com",
                    recipient_list=["castro1985carlos@gmail.com"],
                    fail_silently=True
                )
            except Exception as e:
                print(f"Error al enviar correo de invitación: {e}")

    def __str__(self):
        estado = "Usado" if self.usado else "Activo"
        return f"{self.correo_destino} - {self.tipo_usuario} ({estado})"


# ============================================================
# Usuario (ya existía — se cambia db_table a 'Usuario')
# ============================================================
class Usuario(models.Model):
    dni = models.CharField(primary_key=True, max_length=20, verbose_name="DNI del Usuario")
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True, max_length=100)
    contrasena = models.CharField(max_length=255)
    tipo_usuario = models.CharField(max_length=20, default='normal')
    token_invitacion = models.OneToOneField(
        TokenInvitacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuario_registrado'
    )
    token = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'Usuario'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.nombre} ({self.correo})"


# ============================================================
# Administrador
# ============================================================
class Administrador(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name='administrador'
    )

    class Meta:
        db_table = 'Administrador'
        verbose_name = 'Administrador'
        verbose_name_plural = 'Administradores'

    def __str__(self):
        return f"Admin: {self.usuario.nombre}"


# ============================================================
# Invitado (para usuarios de tipo normal)
# ============================================================
class Invitado(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name='invitado'
    )

    class Meta:
        db_table = 'Invitado'
        verbose_name = 'Invitado'
        verbose_name_plural = 'Invitados'

    def __str__(self):
        return f"Invitado: {self.usuario.nombre}"


# ============================================================
# Categoria
# ============================================================
class Categoria(models.Model):
    codigo = models.CharField(primary_key=True, max_length=50, verbose_name="Código de Categoría")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'Categoria'
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre


# ============================================================
# Proveedor
# ============================================================
class Proveedor(models.Model):
    nit = models.CharField(primary_key=True, max_length=50, verbose_name="NIT del Proveedor")
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    correo = models.EmailField(max_length=100)

    class Meta:
        db_table = 'Proveedor'
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'

    def __str__(self):
        return self.nombre


# ============================================================
# Producto (FK → Categoria)
# ============================================================
class Producto(models.Model):
    dni_producto = models.CharField(primary_key=True, max_length=50, verbose_name="DNI del Producto")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, default='')
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0) # Ahora por defecto es 0 para insumos
    stock = models.IntegerField(default=0)
    es_insumo = models.BooleanField(default=True) # Diferenciar entre materia prima y platos del menú
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='productos'
    )

    class Meta:
        db_table = 'Producto'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Check stock and create notification if it drops below threshold (e.g. 10)
        if self.stock < 10:
            import datetime
            Notificacion.objects.get_or_create(
                mensaje=f"Alerta de Stock Bajo: El producto/insumo {self.nombre} (DNI: {self.dni_producto}) tiene un stock de {self.stock}.",
                fecha=datetime.date.today()
            )

    def __str__(self):
        return f"{self.nombre} (${self.precio})"


# ============================================================
# RecetaInsumo (Relación Plato <-> Insumos de Inventario descontados)
# ============================================================
class RecetaInsumo(models.Model):
    id = models.AutoField(primary_key=True)
    plato = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='ingredientes_receta'
    )
    insumo = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='usado_en_recetas'
    )
    cantidad = models.IntegerField(default=1)

    class Meta:
        db_table = 'RecetaInsumo'
        verbose_name = 'Insumo de Receta'
        verbose_name_plural = 'Insumos de Recetas'

    def __str__(self):
        return f"{self.plato.nombre} - {self.insumo.nombre} (x{self.cantidad})"


# ============================================================
# EntradaProducto (FK → Proveedor, FK → Producto)
# ============================================================
class EntradaProducto(models.Model):
    idEntrada = models.AutoField(primary_key=True)
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.CASCADE,
        related_name='entradas'
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='entradas'
    )
    fechaEntrada = models.DateField(auto_now_add=True)
    cantidad = models.IntegerField()
    precio_compra_unidad = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'EntradaProducto'

    class Meta:
        db_table = 'EntradaProducto'
        verbose_name = 'Entrada de Producto'
        verbose_name_plural = 'Entradas de Productos'

    def __str__(self):
        return f"Entrada #{self.idEntrada} - {self.producto.nombre} x{self.cantidad}"


# ============================================================
# Pedido (FK → Usuario)
# ============================================================
class Pedido(models.Model):
    idPedido = models.AutoField(primary_key=True)
    fecha = models.DateField()
    estado = models.CharField(max_length=50)
    responsableRecepcion = models.CharField(max_length=100, blank=True, null=True)
    direccionEnvio = models.CharField(max_length=255, blank=True, null=True)
    distancia_km = models.FloatField(default=0.0)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wompi_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    wompi_payment_url = models.URLField(max_length=500, blank=True, null=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='pedidos'
    )

    class Meta:
        db_table = 'Pedido'
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'

    def __str__(self):
        return f"Pedido #{self.idPedido} - {self.estado}"


# ============================================================
# DetallePedido (FK → Pedido, FK → Producto)
# ============================================================
class DetallePedido(models.Model):
    idDetalle = models.AutoField(primary_key=True)
    cantidad = models.IntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    cliente = models.CharField(max_length=100)
    cedulaCliente = models.BigIntegerField()
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='detalles'
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='detalles_pedido'
    )

    class Meta:
        db_table = 'DetallePedido'
        verbose_name = 'Detalle de Pedido'
        verbose_name_plural = 'Detalles de Pedidos'

    def __str__(self):
        return f"Detalle #{self.idDetalle} - Pedido #{self.pedido.idPedido}"


# ============================================================
# Inventario (FK → EntradaProducto, FK → Producto, FK → Pedido)
# ============================================================
class Inventario(models.Model):
    idInventario = models.AutoField(primary_key=True)
    entradaDeProducto = models.ForeignKey(
        EntradaProducto,
        on_delete=models.CASCADE,
        related_name='inventarios'
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='inventarios'
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventarios'
    )

    class Meta:
        db_table = 'Inventario'
        verbose_name = 'Inventario'
        verbose_name_plural = 'Inventarios'

    def __str__(self):
        return f"Inventario #{self.idInventario} - {self.producto.nombre}"


# ============================================================
# Factura (FK → Pedido)
# ============================================================
class Factura(models.Model):
    idFactura = models.AutoField(primary_key=True)
    numero_factura = models.CharField(max_length=50, unique=True, null=True, blank=True)
    fecha = models.DateField(auto_now_add=True)
    nit_cliente = models.CharField(max_length=50, blank=True, null=True)
    razon_social = models.CharField(max_length=200, blank=True, null=True)
    metodo_pago = models.CharField(max_length=50, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iva = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_recibido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cambio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='facturas'
    )

    class Meta:
        db_table = 'Factura'
        verbose_name = 'Factura'
        verbose_name_plural = 'Facturas'

    def __str__(self):
        return f"Factura #{self.numero_factura or self.idFactura} - Total: ${self.total}"


# ============================================================
# Facturacion (FK → Pedido, FK → Factura)
# ============================================================
class Facturacion(models.Model):
    idMovimiento = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=50)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='facturaciones'
    )
    fecha = models.DateField()
    factura = models.ForeignKey(
        Factura,
        on_delete=models.CASCADE,
        related_name='facturaciones'
    )

    class Meta:
        db_table = 'Facturacion'
        verbose_name = 'Facturación'
        verbose_name_plural = 'Facturaciones'

    def __str__(self):
        return f"Movimiento #{self.idMovimiento} - {self.tipo}"


# ============================================================
# Caja (FK → Facturacion)
# ============================================================
class Caja(models.Model):
    idCaja = models.AutoField(primary_key=True)
    fechaApertura = models.DateField()
    SaldoInicial = models.DecimalField(max_digits=10, decimal_places=2)
    SaldoFinal = models.DecimalField(max_digits=10, decimal_places=2)
    cantidadFacturaciones = models.IntegerField(default=0)
    facturacion = models.ForeignKey(
        Facturacion,
        on_delete=models.CASCADE,
        related_name='cajas'
    )

    class Meta:
        db_table = 'Caja'
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'

    def __str__(self):
        return f"Caja #{self.idCaja} - {self.fechaApertura}"


# ============================================================
# Notificacion
# ============================================================
class Notificacion(models.Model):
    idNotificacion = models.AutoField(primary_key=True)
    mensaje = models.TextField()
    fecha = models.DateField()

    class Meta:
        db_table = 'Notificacion'
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f"Notificación #{self.idNotificacion}"


# ============================================================
# Reporte
# ============================================================
class Reporte(models.Model):
    idReporte = models.AutoField(primary_key=True)
    fechaGeneracion = models.DateField()
    tipo = models.CharField(max_length=50)
    GeneradoPor = models.CharField(max_length=100)

    class Meta:
        db_table = 'Reporte'
        verbose_name = 'Reporte'
        verbose_name_plural = 'Reportes'

    def __str__(self):
        return f"Reporte #{self.idReporte} - {self.tipo}"
