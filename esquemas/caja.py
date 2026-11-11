from ninja import Schema
from typing import List, Optional
from datetime import date

# ==================== PRODUCTOS ====================
class ProductoCreate(Schema):
    nombre: str
    descripcion: str = ""
    precio: float
    stock: int = 0
    categoria_id: Optional[str] = None

class ProductoResponse(Schema):
    dni_producto: str
    nombre: str
    descripcion: str
    precio: float
    stock: int
    
class CategoriaResponse(Schema):
    codigo: str
    nombre: str

# ==================== PEDIDOS ====================
class DetallePedidoCreate(Schema):
    producto_id: str
    cantidad: int

class DetallePedidoResponse(Schema):
    idDetalle: int
    producto_id: str
    producto_nombre: str
    cantidad: int
    subtotal: float
    cliente: str
    cedulaCliente: int

class PedidoCreate(Schema):
    cliente: str
    cedulaCliente: int
    responsableRecepcion: str
    direccionEnvio: Optional[str] = None
    distancia_km: Optional[float] = 0.0
    costo_envio: Optional[float] = 0.0
    detalles: List[DetallePedidoCreate]

class PedidoUpdate(Schema):
    cliente: Optional[str] = None
    cedulaCliente: Optional[int] = None
    responsableRecepcion: Optional[str] = None
    direccionEnvio: Optional[str] = None
    distancia_km: Optional[float] = None
    costo_envio: Optional[float] = None
    estado: Optional[str] = None
    detalles: Optional[List[DetallePedidoCreate]] = None

class PedidoResponse(Schema):
    idPedido: int
    fecha: date
    estado: str
    responsableRecepcion: Optional[str] = None
    direccionEnvio: Optional[str] = None
    distancia_km: Optional[float] = 0.0
    costo_envio: Optional[float] = 0.0
    usuario_id: str
    total: float
    detalles: List[DetallePedidoResponse]
    wompi_transaction_id: Optional[str] = None
    wompi_payment_url: Optional[str] = None

class CalcularEnvioRequest(Schema):
    direccion: str
    origen: Optional[str] = None

# ==================== FACTURAS ====================
class FacturaResponse(Schema):
    idFactura: int
    fecha: date
    total: float
    pedido_id: int
