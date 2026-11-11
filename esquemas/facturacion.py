from ninja import Schema
from typing import List, Optional
from datetime import date

class FacturaEmitirRequest(Schema):
    pedido_id: int
    nit_cliente: str
    razon_social: str
    metodo_pago: str
    iva_porcentaje: float
    monto_recibido: Optional[float] = 0

class FacturaResponse(Schema):
    idFactura: int
    numero_factura: str
    fecha: date
    nit_cliente: str
    razon_social: str
    metodo_pago: str
    subtotal: float
    iva: float
    total: float
    monto_recibido: float
    cambio: float
    pedido_id: int
    
class PedidoPendienteResponse(Schema):
    idPedido: int
    fecha: date
    cliente: str
    celular_cliente: Optional[str] = None
    estado: str
    total: float

