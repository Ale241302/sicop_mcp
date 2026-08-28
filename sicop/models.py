"""Modelos SICOP - generados desde los esquemas reales de Salidas/."""
from django.db import models


class TimestampedMixin(models.Model):
    ARCHIVO_ORIGEN = models.TextField(blank=True, null=True, db_index=True)
    MES_PUBLICACION = models.TextField(blank=True, null=True, db_index=True)

    class Meta:
        abstract = True


class SicopAdjudicaciones(TimestampedMixin):
    """adjudicaciones - una fila por linea/registro del conjunto."""
    CEDULA = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    ANO = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    DESCR_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    LINEA = models.TextField(blank=True, null=True)
    PROD_ID = models.TextField(blank=True, null=True)
    DESCR_BIEN_SERVICIO = models.TextField(blank=True, null=True)
    CANTIDAD = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    UNIDAD_MEDIDA = models.TextField(blank=True, null=True)
    MONTO_UNITARIO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONEDA_PRECIO_EST = models.TextField(blank=True, null=True)
    MONEDA_ADJUDICADA = models.TextField(blank=True, null=True)
    MONTO_ADJU_LINEA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONTO_ADJU_LINEA_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONTO_ADJU_LINEA_USD = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    FECHA_ADJUD_FIRME = models.DateField(null=True, blank=True)
    FECHA_SOL_CONTRA = models.DateField(null=True, blank=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    PERFIL_PROV = models.TextField(blank=True, null=True)
    CEDULA_REPRESENTANTE = models.TextField(blank=True, null=True)
    REPRESENTANTE = models.TextField(blank=True, null=True)
    OBJETO_GASTO = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    TIPO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    MODALIDAD_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    fecha_rev = models.DateField(null=True, blank=True)
    FECHA_SOL_CONTRA_CL = models.DateField(null=True, blank=True)
    PROD_ID_CL = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_adjudicaciones'
        verbose_name = 'adjudicaciones'


class SicopAdjudicacionesFirme(TimestampedMixin):
    """adjudicaciones_firme - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    FECHA_ADJ_FIRME = models.DateField(null=True, blank=True)
    PERMITE_RECURSOS = models.TextField(blank=True, null=True)
    DESIERTO = models.TextField(blank=True, null=True)
    FECHA_REV = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_adjudicaciones_firme'
        verbose_name = 'adjudicaciones_firme'
        indexes = [models.Index(fields=['NRO_SICOP'])]


class SicopCarteles(TimestampedMixin):
    """carteles - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    FECHA_PUBLICACION = models.DateField(null=True, blank=True)
    NRO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    TIPO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    MODALIDAD_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CARTEL_STAT = models.TextField(blank=True, null=True)
    CARTEL_NM = models.TextField(blank=True, null=True)
    FECHAH_APERTURA = models.DateTimeField(null=True, blank=True)
    CODIGO_BPIP = models.TextField(blank=True, null=True)
    CLAS_OBJ = models.TextField(blank=True, null=True)
    COD_EXCEPCION = models.TextField(blank=True, null=True)
    DES_EXCEPCION = models.TextField(blank=True, null=True)
    MONTO_EST = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    FECHA_MOD = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_carteles'
        verbose_name = 'carteles'
        indexes = [models.Index(fields=['FECHAH_APERTURA']), models.Index(fields=['NRO_SICOP'])]


class SicopContratos(TimestampedMixin):
    """contratos - una fila por linea/registro del conjunto."""
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    TIPO_CONTRATO = models.TextField(blank=True, null=True)
    TIPO_MODIFICACION = models.TextField(blank=True, null=True)
    FECHA_NOTIFICACION = models.DateField(null=True, blank=True)
    FECHA_ELABORACION = models.DateField(null=True, blank=True)
    TIPO_AUTORIZACION = models.TextField(blank=True, null=True)
    TIPO_DISMINUCION = models.TextField(blank=True, null=True)
    VIGENCIA = models.TextField(blank=True, null=True)
    MONEDA = models.TextField(blank=True, null=True)
    FECHA_INI_SUSP = models.DateField(null=True, blank=True)
    FECHA_REINI_CONT = models.DateField(null=True, blank=True)
    PLAZO_SUSP = models.TextField(blank=True, null=True)
    FECHA_MODIFICACION = models.DateField(null=True, blank=True)
    FECHA_INI_PRORR = models.DateField(null=True, blank=True)
    FECHA_FIN_PRORR = models.DateField(null=True, blank=True)
    NRO_CONTRATO_WEB = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_contratos'
        verbose_name = 'contratos'


class SicopEtapas(TimestampedMixin):
    """etapas - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CARTEL_SEQ = models.TextField(blank=True, null=True)
    PARTIDA = models.TextField(blank=True, null=True)
    LINEA = models.TextField(blank=True, null=True)
    PUBLICACION = models.DateField(null=True, blank=True)
    FECHA_APERTURA = models.DateField(null=True, blank=True)
    SOLICITUD_ESTUDIOS_TECNICOS = models.DateField(null=True, blank=True)
    COMUNICACION = models.DateField(null=True, blank=True)
    SOLICITUD_PAGO_ESP_FISCALES = models.DateField(null=True, blank=True)
    RESPUESTA_ESTUDIOS_TECNICOS = models.DateField(null=True, blank=True)
    SOLICITUD_RECOM_ADJUD = models.DateField(null=True, blank=True)
    RESPUESTA_RECOM_ADJUD = models.DateField(null=True, blank=True)
    SOLICITUD_ADJUD = models.DateField(null=True, blank=True)
    RESPUESTA_ADJUD = models.DateField(null=True, blank=True)
    ADJUDICACION_FIRME = models.DateField(null=True, blank=True)
    FECHA_RESUL_PAGO_ESP_FISCALES = models.DateField(null=True, blank=True)
    FECHA_ELABORACION_CONTRATO = models.DateField(null=True, blank=True)
    SOLICITUD_APROBACION_CONTRATO = models.DateField(null=True, blank=True)
    RESPUESTA_APROBACION_CONTRATO = models.DateField(null=True, blank=True)
    FECHA_NOTIFICACION = models.DateField(null=True, blank=True)
    FECHA_1RA_SOL_RECEPCION = models.DateField(null=True, blank=True)
    FECHA_1RA_SOL_RECEP_PROVI = models.DateField(null=True, blank=True)
    FECHA_ULT_SOL_RECEP_DEFI = models.DateField(null=True, blank=True)
    FECHA_1RA_SOL_PAGO = models.DateField(null=True, blank=True)
    FECHA_ULT_SOL_PAGO = models.DateField(null=True, blank=True)
    FECHA_RESUL_PAGO = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_etapas'
        verbose_name = 'etapas'


class SicopEvaluacionOfertas(TimestampedMixin):
    """evaluacion_ofertas - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    EVAL_ITEM_SEQNO = models.TextField(blank=True, null=True)
    FACTOR_EVAL = models.TextField(blank=True, null=True)
    PORC_EVAL = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_evaluacion_ofertas'
        verbose_name = 'evaluacion_ofertas'


class SicopGarantias(TimestampedMixin):
    """garantias - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    DESCRIPCION_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    TIPO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    TIPO_GARANTIA = models.TextField(blank=True, null=True)
    MONTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ESTADO = models.TextField(blank=True, null=True)
    VIGENCIA = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(null=True, blank=True)
    nro_garantia = models.TextField(blank=True, null=True)
    ced_garante = models.TextField(blank=True, null=True)
    gara_seq = models.TextField(blank=True, null=True)
    garantia_NM = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_garantias'
        verbose_name = 'garantias'


class SicopInhibiciones(TimestampedMixin):
    """inhibiciones - una fila por linea/registro del conjunto."""
    CED_INSTITUCION = models.TextField(blank=True, null=True)
    CED_FUNCIONARIO = models.TextField(blank=True, null=True)
    NOM_FUNCIONARIO = models.TextField(blank=True, null=True)
    FECHA_INICIO = models.DateField(null=True, blank=True)
    FECHA_FIN = models.DateField(null=True, blank=True)
    ESTADO = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_inhibiciones'
        verbose_name = 'inhibiciones'


class SicopInstituciones(TimestampedMixin):
    """instituciones - una fila por linea/registro del conjunto."""
    CEDULA = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    ZONA_GEO_INST = models.TextField(blank=True, null=True)
    FECHA_INGRESO = models.DateField(null=True, blank=True)
    FECHA_MOD = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_instituciones'
        verbose_name = 'instituciones'


class SicopProcedimientosAdm(TimestampedMixin):
    """procedimientos_adm - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    NUMERO_PA = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_NOTIFICACION = models.DateField(null=True, blank=True)
    INHAB_APERC = models.TextField(blank=True, null=True)
    MULTA_CAUSULA = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_procedimientos_adm'
        verbose_name = 'procedimientos_adm'


class SicopReajustes(TimestampedMixin):
    """reajustes - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_ELABORACION = models.DateField(null=True, blank=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    DES_PRODUCTO = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    NRO_LINEA_CONTRATO = models.TextField(blank=True, null=True)
    CANTIDAD_CONTRATADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    NUMERO_REAJUSTE = models.TextField(blank=True, null=True)
    PRECIO_ANT_ULT_RJ = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONTO_REAJUSTE = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    NUEVO_PRECIO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PORC_INCR_ULT_RJ = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    FECHA_INICIO = models.DateField(null=True, blank=True)
    FECHA_FIN = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_reajustes'
        verbose_name = 'reajustes'


class SicopRemates(TimestampedMixin):
    """remates - una fila por linea/registro del conjunto."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    FECHA_INVITACION = models.DateField(null=True, blank=True)
    CED_PROVEEDOR = models.TextField(blank=True, null=True)
    MONTO_PUJA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONEDA_PUJA = models.TextField(blank=True, null=True)
    MONTO_EST_LINEA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    CANT_EST = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONEDA_ADJ = models.TextField(blank=True, null=True)
    MONTO_ADJ = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    CANT_ADJ = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_MONEDA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    fecha_mod = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_remates'
        verbose_name = 'remates'


class SicopSancionesRegistro(TimestampedMixin):
    """sanciones_registro - una fila por linea/registro del conjunto."""
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    DESCRIP_PRODUCTO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    TIPO_SANCION = models.TextField(blank=True, null=True)
    DESCR_SANCION = models.TextField(blank=True, null=True)
    INICIO_SANCION = models.DateField(null=True, blank=True)
    FINAL_SANCION = models.DateField(null=True, blank=True)
    ESTADO = models.TextField(blank=True, null=True)
    NO_RESOLUCION = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_sanciones_registro'
        verbose_name = 'sanciones_registro'


class GoldAtributosProducto(models.Model):
    """atributos_producto - tabla derivada."""
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)
    FAMILIA_UNSPSC = models.TextField(blank=True, null=True)
    TIPO_ATRIBUTO = models.TextField(blank=True, null=True)
    VALOR = models.TextField(blank=True, null=True)
    UNIDAD = models.TextField(blank=True, null=True)
    VALOR_NORMALIZADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ES_RANGO = models.TextField(blank=True, null=True)
    CANTIDAD_ADJUDICADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_LINEAS = models.BigIntegerField(null=True, blank=True)
    INSTITUCIONES = models.TextField(blank=True, null=True)
    ANIOS = models.TextField(blank=True, null=True)
    MARCA = models.TextField(blank=True, null=True)
    FUENTE = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_atributos_producto'
        verbose_name = 'atributos_producto'


class GoldBaratoYProrrogadoResumen(models.Model):
    """barato_y_prorrogado_resumen - tabla derivada."""
    POSICION_PRECIO = models.TextField(blank=True, null=True)
    PROCEDIMIENTOS = models.BigIntegerField(null=True, blank=True)
    TASA_MODIFICACION_PCT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TASA_REAJUSTE_PCT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'gold_barato_y_prorrogado_resumen'
        verbose_name = 'barato_y_prorrogado_resumen'


class GoldCarteraProveedor(models.Model):
    """cartera_proveedor - tabla derivada."""
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    ANIO_EJECUCION = models.TextField(blank=True, null=True)
    N_ORDENES_CRC = models.BigIntegerField(null=True, blank=True)
    MONTO_EJECUTADO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_ORDENES_OTRAS_MONEDAS = models.BigIntegerField(null=True, blank=True)
    MONTO_OTRAS_MONEDAS_ORIGEN = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONEDAS = models.TextField(blank=True, null=True)
    N_SOSPECHOSAS = models.BigIntegerField(null=True, blank=True)
    MONTO_SOSPECHOSO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_PROCEDIMIENTOS_ACTIVOS = models.BigIntegerField(null=True, blank=True)
    PCT_DE_ANIOS_ANTERIORES = models.TextField(blank=True, null=True)
    ANTIGUEDAD_MAX_ANIOS = models.BigIntegerField(null=True, blank=True)
    ORIGEN_POR_ANIO = models.TextField(blank=True, null=True)
    MONTO_ADJUDICADO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    RATIO_EJECUCION_CAPTACION = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ESTADOS_ORDEN = models.TextField(blank=True, null=True)
    NIVEL_DE_MEDICION = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_cartera_proveedor'
        verbose_name = 'cartera_proveedor'


class GoldCarteraResumen(models.Model):
    """cartera_resumen - tabla derivada."""
    ANIO = models.TextField(blank=True, null=True)
    MONTO_EJECUTADO_TOTAL_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONTO_ADJUDICADO_TOTAL_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    RATIO_EJECUCION_CAPTACION = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PCT_EJECUCION_ANIOS_PREVIOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_ORDENES_CRC = models.BigIntegerField(null=True, blank=True)
    N_PROVEEDORES = models.BigIntegerField(null=True, blank=True)
    N_ORDENES_OTRAS_MONEDAS = models.BigIntegerField(null=True, blank=True)
    MONTO_OTRAS_MONEDAS_ORIGEN = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_ORDENES_SOSPECHOSAS = models.BigIntegerField(null=True, blank=True)
    MONTO_SOSPECHOSO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'gold_cartera_resumen'
        verbose_name = 'cartera_resumen'


class GoldCatalogoProductos(models.Model):
    """catalogo_productos - tabla derivada."""
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)
    FAMILIA_UNSPSC = models.TextField(blank=True, null=True)
    DESCRIPCION = models.TextField(blank=True, null=True)
    MARCA = models.TextField(blank=True, null=True)
    MODELO = models.TextField(blank=True, null=True)
    PATRON_MATCH = models.TextField(blank=True, null=True)
    MARCA_PLAUSIBLE = models.TextField(blank=True, null=True)
    LINEAS_EJECUCION = models.BigIntegerField(null=True, blank=True)
    PROCEDIMIENTOS = models.BigIntegerField(null=True, blank=True)
    PROVEEDORES_ADJUDICADOS = models.BigIntegerField(null=True, blank=True)
    PROVEEDOR_TOP = models.TextField(blank=True, null=True)
    INSTITUCIONES = models.TextField(blank=True, null=True)
    ANIOS_ADJUDICACION = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_catalogo_productos'
        verbose_name = 'catalogo_productos'


class GoldCompetenciaPorLinea(models.Model):
    """competencia_por_linea - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_PRESENTA_OFERTA = models.TextField(blank=True, null=True)
    TIPO_OFERTA = models.TextField(blank=True, null=True)
    ID_CONSORCIO = models.TextField(blank=True, null=True)
    CANTIDAD_OFERTADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO_OFERTADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_MONEDA = models.TextField(blank=True, null=True)
    TIPO_CAMBIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_SOSPECHOSO = models.TextField(blank=True, null=True)
    ES_ADJUDICATARIO = models.TextField(blank=True, null=True)
    MES_PUBLICACION = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_competencia_por_linea'
        verbose_name = 'competencia_por_linea'


class GoldDesempenoProveedor(models.Model):
    """desempeno_proveedor - tabla derivada."""
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    TAMANO_PROVEEDOR = models.TextField(blank=True, null=True)
    LINEAS_RECIBIDAS = models.BigIntegerField(null=True, blank=True)
    N_CUMPLE = models.BigIntegerField(null=True, blank=True)
    N_NO_CUMPLE = models.BigIntegerField(null=True, blank=True)
    N_NO_CUMPLE_PAGO_PARCIAL = models.BigIntegerField(null=True, blank=True)
    TASA_CUMPLIMIENTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    DIAS_MEDIANO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    DIAS_P90 = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PCT_CON_ATRASO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    RATIO_ENTREGA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    INSTITUCIONES = models.BigIntegerField(null=True, blank=True)
    ANIOS_ACTIVO = models.BigIntegerField(null=True, blank=True)
    FAMILIAS_UNSPSC = models.TextField(blank=True, null=True)
    MUESTRA_SUFICIENTE = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_desempeno_proveedor'
        verbose_name = 'desempeno_proveedor'


class GoldDesempenoPorFamilia(models.Model):
    """desempeno_por_familia - tabla derivada."""
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    FAMILIA_UNSPSC = models.TextField(blank=True, null=True)
    LINEAS_RECIBIDAS = models.BigIntegerField(null=True, blank=True)
    N_CUMPLE = models.BigIntegerField(null=True, blank=True)
    TASA_CUMPLIMIENTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    DIAS_MEDIANO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MUESTRA_SUFICIENTE = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_desempeno_por_familia'
        verbose_name = 'desempeno_por_familia'


class GoldExcepcionesPorAdjudicatario(models.Model):
    """excepciones_por_adjudicatario - tabla derivada."""
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    CAUSAL_EXCEPCION = models.TextField(blank=True, null=True)
    COD_EXCEPCION = models.TextField(blank=True, null=True)
    PROCEDIMIENTOS = models.BigIntegerField(null=True, blank=True)
    LINEAS_ADJUDICADAS = models.BigIntegerField(null=True, blank=True)
    INSTITUCIONES = models.BigIntegerField(null=True, blank=True)
    MONTO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MESES = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_excepciones_por_adjudicatario'
        verbose_name = 'excepciones_por_adjudicatario'


class GoldExpedienteTrazabilidad(models.Model):
    """expediente_trazabilidad - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    T_CARTEL = models.TextField(blank=True, null=True)
    T_OFERTAS = models.TextField(blank=True, null=True)
    T_ACTO_FIRME = models.TextField(blank=True, null=True)
    T_ADJUDICADO = models.TextField(blank=True, null=True)
    T_CONTRATO = models.TextField(blank=True, null=True)
    T_GARANTIA = models.TextField(blank=True, null=True)
    T_RECIBIDO = models.TextField(blank=True, null=True)
    NUM_TRAMOS = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'gold_expediente_trazabilidad'
        verbose_name = 'expediente_trazabilidad'


class GoldInvitacionesConcentracion(models.Model):
    """invitaciones_concentracion - tabla derivada."""
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    PROCEDIMIENTOS = models.BigIntegerField(null=True, blank=True)
    INVITACIONES = models.BigIntegerField(null=True, blank=True)
    INVITADOS_DISTINTOS = models.BigIntegerField(null=True, blank=True)
    TOP1 = models.TextField(blank=True, null=True)
    TOP2 = models.TextField(blank=True, null=True)
    TOP3 = models.TextField(blank=True, null=True)
    PARTICIPACION_TOP3_PCT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'gold_invitaciones_concentracion'
        verbose_name = 'invitaciones_concentracion'


class GoldPrecioPorInstitucion(models.Model):
    """precio_por_institucion - tabla derivada."""
    MARCA = models.TextField(blank=True, null=True)
    MODELO = models.TextField(blank=True, null=True)
    ATRIBUTOS_CLAVE = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)
    FAMILIA_UNSPSC = models.TextField(blank=True, null=True)
    ANIO = models.TextField(blank=True, null=True)
    N_ADJUDICACIONES = models.BigIntegerField(null=True, blank=True)
    INSTITUCIONES_DISTINTAS = models.BigIntegerField(null=True, blank=True)
    PU_CRC_MEDIANO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PU_USD_MEDIANO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PU_CRC_MIN = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PU_CRC_MAX = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    RATIO_MAX_MIN = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    INSTITUCION_MAS_CARA = models.TextField(blank=True, null=True)
    PU_MAS_CARA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    INSTITUCION_MAS_BARATA = models.TextField(blank=True, null=True)
    PU_MAS_BARATA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'gold_precio_por_institucion'
        verbose_name = 'precio_por_institucion'


class GoldRankingCaptacionEjecucion(models.Model):
    """ranking_captacion_ejecucion - tabla derivada."""
    POSICION = models.BigIntegerField(null=True, blank=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    MONTO_ADJUDICADO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONTO_EJECUTADO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    RATIO_EJECUCION_CAPTACION = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_ORDENES_CRC = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'gold_ranking_captacion_ejecucion'
        verbose_name = 'ranking_captacion_ejecucion'


class GoldRepresentanteCompetencia(models.Model):
    """representante_competencia - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    ANIO = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    CEDULA_REPRESENTANTE = models.TextField(blank=True, null=True)
    REPRESENTANTE = models.TextField(blank=True, null=True)
    N_EMPRESAS_MISMO_REP = models.BigIntegerField(null=True, blank=True)
    EMPRESAS = models.TextField(blank=True, null=True)
    PRECIOS_OFERTADOS_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ADJUDICATARIO = models.TextField(blank=True, null=True)
    ADJUDICATARIO_COMPARTE_REP = models.TextField(blank=True, null=True)
    N_OFERENTES_TOTAL = models.BigIntegerField(null=True, blank=True)
    ADVERTENCIA = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_representante_competencia'
        verbose_name = 'representante_competencia'


class GoldRepresentanteEmpresas(models.Model):
    """representante_empresas - tabla derivada."""
    CEDULA_REPRESENTANTE = models.TextField(blank=True, null=True)
    REPRESENTANTE = models.TextField(blank=True, null=True)
    N_EMPRESAS = models.BigIntegerField(null=True, blank=True)
    EMPRESAS = models.TextField(blank=True, null=True)
    N_ADJUDICACIONES = models.BigIntegerField(null=True, blank=True)
    MONTO_TOTAL_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    INSTITUCIONES = models.TextField(blank=True, null=True)
    FAMILIAS = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_representante_empresas'
        verbose_name = 'representante_empresas'


class GoldSancionesProveedores(models.Model):
    """sanciones_proveedores - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    CEDULAS_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRES_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_NOTIFICACION = models.TextField(blank=True, null=True)
    INHAB_APERC = models.TextField(blank=True, null=True)
    MULTA_CAUSULA = models.TextField(blank=True, null=True)
    N_NOTIFICACIONES = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'gold_sanciones_proveedores'
        verbose_name = 'sanciones_proveedores'


class GoldCartelesObjetados(models.Model):
    """carteles_objetados - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    TIPO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    MODALIDAD_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    MONTO_EST = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    FECHA_PUBLICACION = models.DateField(null=True, blank=True)
    FECHAH_APERTURA = models.DateTimeField(null=True, blank=True)
    SE_ADJUDICO = models.TextField(blank=True, null=True)
    FECHA_ADJUDICACION = models.DateField(null=True, blank=True)
    MES_PUBLICACION = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_carteles_objetados'
        verbose_name = 'carteles_objetados'


class GoldBaratoYProrrogado(models.Model):
    """barato_y_prorrogado - tabla derivada."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    ANIO = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    ADJUDICATARIO = models.TextField(blank=True, null=True)
    POSICION_PRECIO = models.BigIntegerField(null=True, blank=True)
    N_OFERENTES = models.BigIntegerField(null=True, blank=True)
    DELTA_VS_MEDIANA_PCT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIENE_CONTRATO = models.TextField(blank=True, null=True)
    TIPO_CONTRATO = models.TextField(blank=True, null=True)
    N_MODIFICACIONES = models.BigIntegerField(null=True, blank=True)
    TIPO_MODIFICACION = models.TextField(blank=True, null=True)
    TIENE_REAJUSTE = models.TextField(blank=True, null=True)
    PCT_REAJUSTE = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'gold_barato_y_prorrogado'
        verbose_name = 'barato_y_prorrogado'



class LoadState(models.Model):
    table_name = models.TextField()
    file_path = models.TextField()
    sha256 = models.TextField()
    rows_loaded = models.BigIntegerField(default=0)
    coerced_cells = models.BigIntegerField(default=0)
    loaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sicop_load_state'
        constraints = [models.UniqueConstraint(fields=['table_name', 'file_path'], name='uniq_load_file')]



# --- conjuntos recuperados (extraccion desde Observatorio + invitaciones) ---

class SicopOfertas(TimestampedMixin):
    """sicop_ofertas."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_PRESENTA_OFERTA = models.DateField(null=True, blank=True)
    TIPO_OFERTA = models.TextField(blank=True, null=True)
    ID_CONSORCIO = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_ofertas'


class SicopLineasCartel(TimestampedMixin):
    """sicop_lineas_cartel."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_LINEA = models.TextField(blank=True, null=True)
    NUMERO_PARTIDA = models.TextField(blank=True, null=True)
    CANTIDAD_SOLICITADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO_ESTIMADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_MONEDA = models.TextField(blank=True, null=True)
    TIPO_CAMBIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_DOLAR = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    CODIGO_IDENTIFICACION = models.TextField(blank=True, null=True)
    MONTO_RESERVADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    DESC_LINEA = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_lineas_cartel'


class SicopLineasOfertadas(TimestampedMixin):
    """sicop_lineas_ofertadas."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    CANTIDAD_OFERTADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO_OFERTADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_MONEDA = models.TextField(blank=True, null=True)
    DESCUENTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    IVA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    OTROS_IMPUESTOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ACARREOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_DOLAR = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_lineas_ofertadas'


class SicopLineasAdjudicadas(TimestampedMixin):
    """sicop_lineas_adjudicadas."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    CANTIDAD_ADJUDICADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO_ADJUDICADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_MONEDA = models.TextField(blank=True, null=True)
    DESCUENTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    IVA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    OTROS_IMPUESTOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ACARREOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_DOLAR = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'sicop_lineas_adjudicadas'


class SicopLineasContratadas(TimestampedMixin):
    """sicop_lineas_contratadas."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_LINEA_CONTRATO = models.TextField(blank=True, null=True)
    NRO_LINEA_CARTEL = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    CANTIDAD_CONTRATADA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    PRECIO_UNITARIO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_MONEDA = models.TextField(blank=True, null=True)
    DESCUENTO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    IVA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    OTROS_IMPUESTOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ACARREOS = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TIPO_CAMBIO_DOLAR = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    DESC_PRODUCTO = models.TextField(blank=True, null=True)
    cantidad_aumentada = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    cantidad_disminuida = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    monto_aumentado = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    monto_disminuido = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'sicop_lineas_contratadas'


class SicopLineasRecibidas(TimestampedMixin):
    """sicop_lineas_recibidas."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    NRO_RECEP_PROVISIONAL = models.TextField(blank=True, null=True)
    ESTADO_RECEP_PROVISIONAL = models.TextField(blank=True, null=True)
    NRO_RECEP_DEFINITIVA = models.TextField(blank=True, null=True)
    ESTADO_RECEP_DEFINITIVA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    ENTREGA = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    CANTIDAD_REAL_RECIBIDA = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    desc_producto = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    dias_adelanto_atraso = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    fecha_recepcion_Definitiva = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_lineas_recibidas'


class SicopRecursos(TimestampedMixin):
    """sicop_recursos."""
    NRO_RECURSO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    LINEA_OBJETADA = models.TextField(blank=True, null=True)
    TIPO_RECURSO = models.TextField(blank=True, null=True)
    RESULTADO = models.TextField(blank=True, null=True)
    CAUSA_RESULTADO = models.TextField(blank=True, null=True)
    FECHA_PRESENTACION_RECURSO = models.DateField(null=True, blank=True)
    nro_procedimiento = models.TextField(blank=True, null=True)
    desc_procedimiento = models.TextField(blank=True, null=True)
    reqer_nm = models.TextField(blank=True, null=True)
    recurso_stat = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_recursos'


class SicopProveedores(TimestampedMixin):
    """sicop_proveedores."""
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    TIPO_PROVEEDOR = models.TextField(blank=True, null=True)
    TAMAÑO_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_CONSTITUCION = models.DateField(null=True, blank=True)
    FECHA_EXPIRACION = models.DateField(null=True, blank=True)
    zona_geo_prov = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(null=True, blank=True)
    fecha_mod = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_proveedores'


class SicopRecepciones(TimestampedMixin):
    """sicop_recepciones."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    NRO_RECEP_DEFINITIVA = models.TextField(blank=True, null=True)
    FECHA_RECEP_DEFINITIVA = models.DateField(null=True, blank=True)
    nro_procedimiento = models.TextField(blank=True, null=True)
    cedula_proveedor = models.TextField(blank=True, null=True)
    cedula_institucion = models.TextField(blank=True, null=True)
    moneda = models.TextField(blank=True, null=True)
    nombre_proveedor = models.TextField(blank=True, null=True)
    fecha_ent_ini = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_recepciones'


class SicopOrdenesPedido(TimestampedMixin):
    """sicop_ordenes_pedido."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    CONTRACT_NO = models.TextField(blank=True, null=True)
    SECUENCIA_CONTRATO = models.TextField(blank=True, null=True)
    TOTAL_ORDEN = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    TOTALESTIMADO = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    USD_MONT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    MONEDA_ORDEN = models.TextField(blank=True, null=True)
    NRO_ORDEN = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    LINEA_ORD_PEDIDO = models.TextField(blank=True, null=True)
    ESTADO_ORDEN = models.TextField(blank=True, null=True)
    DESC_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    FECHA_ELABORACION_ORDEN = models.DateField(null=True, blank=True)
    FECHA_NOTIFICACION_ORDEN = models.DateField(null=True, blank=True)
    FECHA_PROVEEDOR_RECIBE_ORDEN = models.DateField(null=True, blank=True)
    FECHA_PROV_RECIBE_ORDEN = models.DateField(null=True, blank=True)
    FECHA_REC_PEDIDO = models.DateField(null=True, blank=True)
    FECHAREGISTRO = models.DateField(null=True, blank=True)
    CEDULAPROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sicop_ordenes_pedido'


class SicopInvitaciones(TimestampedMixin):
    """sicop_invitaciones."""
    SECUENCIA = models.BigIntegerField(null=True, blank=True)
    CED_INSTITUCION = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    FECHA_INVITACION = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sicop_invitaciones'



# --- derivadas recuperadas (plan: recursos_desenlace, tiempos_por_etapa, precios_identicos, producto_firma, invitados_vs_ofertantes) ---

class GoldRecursosDesenlace(models.Model):
    """gold_recursos_desenlace."""
    NRO_RECURSO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    TAMANO_PROVEEDOR = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    LINEA_OBJETADA = models.TextField(blank=True, null=True)
    TIPO_RECURSO = models.TextField(blank=True, null=True)
    RESULTADO = models.TextField(blank=True, null=True)
    CAUSA_RESULTADO = models.TextField(blank=True, null=True)
    FECHA_PRESENTACION_RECURSO = models.DateField(null=True, blank=True)
    PROSPERO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    NOMBRE_INSTITUCION = models.TextField(blank=True, null=True)
    nro_procedimiento = models.TextField(blank=True, null=True)
    desc_procedimiento = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_recursos_desenlace'


class GoldTiemposPorEtapa(models.Model):
    """gold_tiempos_por_etapa."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    FECHA_PUBLICACION = models.TextField(blank=True, null=True)
    FECHA_APERTURA = models.TextField(blank=True, null=True)
    FECHA_ADJUDICACION = models.TextField(blank=True, null=True)
    FECHA_CONTRATO = models.TextField(blank=True, null=True)
    FECHA_RECEPCION = models.TextField(blank=True, null=True)
    DIAS_PUBLICACION_APERTURA = models.BigIntegerField(null=True, blank=True)
    DIAS_PUBLICACION_ADJUDICACION = models.BigIntegerField(null=True, blank=True)
    DIAS_ADJUDICACION_CONTRATO = models.BigIntegerField(null=True, blank=True)
    DIAS_PUBLICACION_RECEPCION = models.BigIntegerField(null=True, blank=True)
    N_TRAMOS = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'gold_tiempos_por_etapa'


class GoldPreciosIdenticos(models.Model):
    """gold_precios_identicos."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    ANIO = models.TextField(blank=True, null=True)
    PRECIO_CRC = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    N_OFERENTES_IGUAL = models.BigIntegerField(null=True, blank=True)
    N_TOTAL_OFERENTES = models.BigIntegerField(null=True, blank=True)
    PAR_OFERENTES = models.TextField(blank=True, null=True)
    REPETICION_PAR = models.BigIntegerField(null=True, blank=True)
    ADVERTENCIA = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_precios_identicos'


class GoldProductoFirma(models.Model):
    """gold_producto_firma."""
    CODIGO_PRODUCTO_CL = models.TextField(blank=True, null=True)
    FAMILIA_UNSPSC = models.TextField(blank=True, null=True)
    MARCA = models.TextField(blank=True, null=True)
    MODELO = models.TextField(blank=True, null=True)
    ATRIBUTOS_CLAVE = models.TextField(blank=True, null=True)
    N_ATRIBUTOS = models.BigIntegerField(null=True, blank=True)
    N_SKUS = models.BigIntegerField(null=True, blank=True)
    FIRMA_SKU = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_producto_firma'


class GoldInvitadosVsOfertantes(models.Model):
    """gold_invitados_vs_ofertantes."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_PROCEDIMIENTO = models.TextField(blank=True, null=True)
    CEDULA_INSTITUCION = models.TextField(blank=True, null=True)
    INSTITUCION = models.TextField(blank=True, null=True)
    N_INVITADOS = models.BigIntegerField(null=True, blank=True)
    N_OFERTARON = models.BigIntegerField(null=True, blank=True)
    N_INVITADOS_QUE_NO_OFERTARON = models.BigIntegerField(null=True, blank=True)
    N_OFERTARON_SIN_INVITACION = models.BigIntegerField(null=True, blank=True)
    TASA_RESPUESTA_PCT = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    ADJUDICATARIO_FUE_INVITADO = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_invitados_vs_ofertantes'



# --- FASE 0: regimen de evaluacion + ctl_deriva ---

class GoldRegimenEvaluacion(models.Model):
    """gold_regimen_evaluacion."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    N_FACTORES = models.BigIntegerField(null=True, blank=True)
    PRECIO_PCT = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    REGIMEN = models.TextField(blank=True, null=True)
    FACTORES_NORMALIZADOS = models.TextField(blank=True, null=True)
    PESOS = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'gold_regimen_evaluacion'


class GoldCompetenciaPorRegimen(models.Model):
    """gold_competencia_por_regimen."""
    REGIMEN = models.TextField(blank=True, null=True)
    N_LINEAS = models.BigIntegerField(null=True, blank=True)
    PCT_GANA_MAS_BARATO = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    PCT_GANA_MAS_CARO = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    MEDIANA_DELTA_PCT = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    N_OFERENTES_MEDIANO = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'gold_competencia_por_regimen'


class CtlDeriva(models.Model):
    """ctl_deriva."""
    CONJUNTO = models.TextField(blank=True, null=True)
    CAMPO = models.TextField(blank=True, null=True)
    ANIO = models.TextField(blank=True, null=True)
    PRESENTE = models.TextField(blank=True, null=True)
    LLENADO_PCT = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ES_CLAVE = models.TextField(blank=True, null=True)
    SIGNIFICADO = models.TextField(blank=True, null=True)
    TRAMPA = models.TextField(blank=True, null=True)
    VERIFICADO_EN = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ctl_deriva'



# --- FASE 1: bronze + ctl + catalogo_campo + 6 hechos silver ---
from datetime import datetime
from django.utils import timezone


class BronzeFila(models.Model):
    """bronze_fila."""
    CONJUNTO = models.TextField(blank=True, null=True)
    MES = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)
    ARCHIVO = models.TextField(blank=True, null=True)
    LINEA_FISICA = models.BigIntegerField(null=True, blank=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    FILA_CRUDA = models.TextField(blank=True, null=True)
    OBSERVADO_EN = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'bronze_fila'
        indexes = [models.Index(fields=['CONJUNTO', 'MES'])]


class CtlCorrida(models.Model):
    """ctl_corrida."""
    CORRIDA_ID = models.TextField(blank=True, null=True)
    ESTADO = models.TextField(blank=True, null=True)
    ALCANCE = models.TextField(blank=True, null=True)
    NOTAS = models.TextField(blank=True, null=True)
    INICIADO_EN = models.DateTimeField(null=True, blank=True)
    CERRADO_EN = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ctl_corrida'


class CtlMesFuente(models.Model):
    """ctl_mes_fuente."""
    AAAAMM = models.TextField(blank=True, null=True)
    HASH_ZIP = models.TextField(blank=True, null=True)
    TAMANO_BYTES = models.BigIntegerField(null=True, blank=True)
    PROCESADO_EN = models.DateTimeField(null=True, blank=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ctl_mes_fuente'


class CtlEsquema(models.Model):
    """ctl_esquema."""
    TABLA = models.TextField(blank=True, null=True)
    COLUMNAS_VISTAS = models.TextField(blank=True, null=True)
    PRIMERA_VEZ = models.DateTimeField(null=True, blank=True)
    ULTIMA_VEZ = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ctl_esquema'


class CtlCuarentena(models.Model):
    """ctl_cuarentena."""
    CORRIDA_ID = models.TextField(blank=True, null=True)
    TABLA = models.TextField(blank=True, null=True)
    ARCHIVO = models.TextField(blank=True, null=True)
    LINEA = models.BigIntegerField(null=True, blank=True)
    MOTIVO = models.TextField(blank=True, null=True)
    FILA_CRUDA = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ctl_cuarentena'


class CtlTest(models.Model):
    """ctl_test."""
    CORRIDA_ID = models.TextField(blank=True, null=True)
    TEST = models.TextField(blank=True, null=True)
    RESULTADO = models.TextField(blank=True, null=True)
    VALOR_OBTENIDO = models.TextField(blank=True, null=True)
    UMBRAL = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ctl_test'


class CatalogoCampo(models.Model):
    """catalogo_campo."""
    TABLA = models.TextField(blank=True, null=True)
    CAMPO = models.TextField(blank=True, null=True)
    TIPO = models.TextField(blank=True, null=True)
    ES_CLAVE = models.TextField(blank=True, null=True)
    LLENADO_PCT = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    CARDINALIDAD = models.BigIntegerField(null=True, blank=True)
    SIGNIFICADO = models.TextField(blank=True, null=True)
    TRAMPA = models.TextField(blank=True, null=True)
    UNIDAD = models.TextField(blank=True, null=True)
    REGLA_JOIN = models.TextField(blank=True, null=True)
    VERIFICADO_EN = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'catalogo_campo'
        indexes = [models.Index(fields=['TABLA'])]


class FactRequerimiento(models.Model):
    """fact_requerimiento."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NUMERO_LINEA = models.TextField(blank=True, null=True)
    NUMERO_PARTIDA = models.TextField(blank=True, null=True)
    CODIGO_CL = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    DESC_LINEA = models.TextField(blank=True, null=True)
    CANTIDAD_SOLICITADA = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    PU_ESTIMADO_ORIG = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    MONEDA_ESTIMADO = models.TextField(blank=True, null=True)
    TC_ESTIMADO = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    PU_ESTIMADO_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_requerimiento'
        indexes = [models.Index(fields=['NRO_SICOP', 'NUMERO_LINEA'])]


class FactOferta(models.Model):
    """fact_oferta."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    CODIGO_CL = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    CANTIDAD_OFERTADA = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    PU_OFERTADO_ORIG = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    MONEDA_OFERTA = models.TextField(blank=True, null=True)
    TC_OFERTA = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    PU_OFERTADO_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ES_CONSORCIO = models.TextField(blank=True, null=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_oferta'
        indexes = [models.Index(fields=['NRO_SICOP', 'NRO_OFERTA'])]


class FactAdjudicacion(models.Model):
    """fact_adjudicacion."""
    NRO_SICOP = models.TextField(blank=True, null=True)
    NRO_ACTO = models.TextField(blank=True, null=True)
    NRO_OFERTA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    NOMBRE_PROVEEDOR = models.TextField(blank=True, null=True)
    CODIGO_CL = models.TextField(blank=True, null=True)
    PROD_ID = models.TextField(blank=True, null=True)
    DESCR_BIEN_SERVICIO = models.TextField(blank=True, null=True)
    CANTIDAD_ADJUDICADA = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    PU_ADJUDICADO_ORIG = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    MONEDA_ADJUDICACION = models.TextField(blank=True, null=True)
    TC_ADJUDICACION = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    PU_ADJUDICADO_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    MONTO_ADJUDICADO_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    OBJETO_GASTO = models.TextField(blank=True, null=True)
    FECHA_ADJUD_FIRME = models.DateField(null=True, blank=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_adjudicacion'
        indexes = [models.Index(fields=['NRO_SICOP', 'CEDULA_PROVEEDOR'])]


class FactContratoLinea(models.Model):
    """fact_contrato_linea."""
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    NRO_LINEA_CARTEL = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    CODIGO_CL = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    DESC_PRODUCTO = models.TextField(blank=True, null=True)
    CANTIDAD_CONTRATADA = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    PU_CONTRATADO_ORIG = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    MONEDA_CONTRATO = models.TextField(blank=True, null=True)
    TC_CONTRATO = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    PU_CONTRATADO_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_contrato_linea'
        indexes = [models.Index(fields=['NRO_CONTRATO', 'NRO_SICOP'])]


class FactOrden(models.Model):
    """fact_orden."""
    NRO_ORDEN = models.TextField(blank=True, null=True)
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    CEDULA_PROVEEDOR = models.TextField(blank=True, null=True)
    FECHA_ELABORACION = models.DateField(null=True, blank=True)
    MONEDA_ORDEN = models.TextField(blank=True, null=True)
    TOTAL_ORDEN_ORIG = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    TC_APLICADO = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    TOTAL_ORDEN_CRC = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ES_OUTLIER = models.TextField(blank=True, null=True)
    ESTADO_ORDEN = models.TextField(blank=True, null=True)
    N_LINEAS = models.BigIntegerField(null=True, blank=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_orden'
        indexes = [models.Index(fields=['NRO_ORDEN'])]


class FactRecepcion(models.Model):
    """fact_recepcion."""
    NRO_CONTRATO = models.TextField(blank=True, null=True)
    SECUENCIA = models.TextField(blank=True, null=True)
    NRO_LINEA = models.TextField(blank=True, null=True)
    NRO_SICOP = models.TextField(blank=True, null=True)
    CODIGO_CL = models.TextField(blank=True, null=True)
    CODIGO_PRODUCTO = models.TextField(blank=True, null=True)
    DESC_PRODUCTO = models.TextField(blank=True, null=True)
    CANTIDAD_REAL_RECIBIDA = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ESTADO_RECEP_DEFINITIVA = models.TextField(blank=True, null=True)
    DIAS_ADELANTO_ATRASO = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    FECHA_RECEPCION = models.DateField(null=True, blank=True)
    OBSERVADO_DESDE = models.DateTimeField(null=True, blank=True)
    OBSERVADO_HASTA = models.DateTimeField(null=True, blank=True)
    ES_VIGENTE = models.BooleanField(default=True)
    HASH_FILA = models.TextField(blank=True, null=True)
    CORRIDA_ID = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'fact_recepcion'
        indexes = [models.Index(fields=['NRO_CONTRATO'])]





# --- FASE 2: resultado_decision + senales + vigilancia ---
import uuid


class ResultadoDecision(models.Model):
    """resultado_decision."""
    resultado_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nro_sicop = models.TextField(blank=True, null=True)
    nro_linea = models.TextField(blank=True, null=True)
    codigo_producto_cl = models.TextField(blank=True, null=True)
    cl_origen = models.TextField(blank=True, null=True)
    institucion_cedula = models.TextField(blank=True, null=True)
    institucion_nombre = models.TextField(blank=True, null=True)
    fecha_invitacion = models.DateTimeField(null=True, blank=True)
    canal_entrada = models.TextField(blank=True, null=True)
    fecha_apertura = models.DateTimeField(null=True, blank=True)
    regimen = models.TextField(blank=True, null=True)
    build_id = models.TextField(blank=True, null=True)
    snapshot_ts = models.DateTimeField(null=True, blank=True)
    modelo_version = models.TextField(blank=True, null=True)
    features_hash = models.TextField(blank=True, null=True)
    features_json = models.TextField(blank=True, null=True)
    n_oferentes_esperados = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    precio_ancla_pliego = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    precio_recomendado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    moneda_recomendada = models.TextField(blank=True, null=True)
    prob_exito_estimada = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    prob_ic_bajo = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    prob_ic_alto = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    decision = models.TextField(blank=True, null=True)
    fecha_decision = models.DateTimeField(null=True, blank=True)
    decidido_por = models.TextField(blank=True, null=True)
    motivo_no_ofertar = models.TextField(blank=True, null=True)
    motivo_texto = models.TextField(blank=True, null=True)
    override = models.BooleanField(default=False)
    override_motivo = models.TextField(blank=True, null=True)
    precio_ofertado_final = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    moneda_ofertada = models.TextField(blank=True, null=True)
    tipo_cambio_crc = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    precio_ofertado_crc = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    fecha_presentacion = models.DateTimeField(null=True, blank=True)
    nro_oferta = models.TextField(blank=True, null=True)
    estado_resultado = models.TextField(blank=True, null=True)
    fecha_resultado = models.DateField(null=True, blank=True)
    n_oferentes_real = models.BigIntegerField(null=True, blank=True)
    cedula_ganador = models.TextField(blank=True, null=True)
    precio_ganador = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    moneda_ganador = models.TextField(blank=True, null=True)
    precio_ganador_crc = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    posicion_precio = models.BigIntegerField(null=True, blank=True)
    brecha_vs_ganador = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    fuente_resultado = models.TextField(blank=True, null=True)
    fecha_observacion = models.DateTimeField(null=True, blank=True)
    hash_fila = models.TextField(blank=True, null=True)
    observado_desde = models.DateTimeField(null=True, blank=True)
    observado_hasta = models.DateTimeField(null=True, blank=True)
    es_vigente = models.BooleanField(default=False)
    corrida_id = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'resultado_decision'
        indexes = [models.Index(fields=['nro_sicop']), models.Index(fields=['nro_linea']), models.Index(fields=['estado_resultado'])]


class Senal(models.Model):
    """senal."""
    fecha = models.DateTimeField(null=True, blank=True)
    corrida = models.TextField(blank=True, null=True)
    tipo = models.TextField(blank=True, null=True)
    prioridad = models.TextField(blank=True, null=True)
    nro_sicop = models.TextField(blank=True, null=True)
    nro_linea = models.TextField(blank=True, null=True)
    titulo = models.TextField(blank=True, null=True)
    detalle = models.TextField(blank=True, null=True)
    evidencia = models.TextField(blank=True, null=True)
    estado = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'senal'
        indexes = [models.Index(fields=['tipo']), models.Index(fields=['estado'])]


class VigilanciaCheck(models.Model):
    """vigilancia_check."""
    aaaamm = models.TextField(blank=True, null=True)
    etag = models.TextField(blank=True, null=True)
    content_length = models.BigIntegerField(null=True, blank=True)
    sha256 = models.TextField(blank=True, null=True)
    resultado = models.TextField(blank=True, null=True)
    detalle = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(null=True, blank=True)
    corrida = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'vigilancia_check'



# --- FASE 3: registro de respuestas ---

class RegistroRespuesta(models.Model):
    """registro_respuesta."""
    timestamp = models.DateTimeField(null=True, blank=True)
    agente = models.TextField(blank=True, null=True)
    herramienta = models.TextField(blank=True, null=True)
    parametros = models.TextField(blank=True, null=True)
    build_id = models.TextField(blank=True, null=True)
    conteo = models.BigIntegerField(null=True, blank=True)
    calidad = models.TextField(blank=True, null=True)
    carril = models.TextField(blank=True, null=True)
    corrida = models.TextField(blank=True, null=True)
    duracion_ms = models.BigIntegerField(null=True, blank=True)
    status = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'registro_respuesta'
        indexes = [models.Index(fields=('herramienta',)), models.Index(fields=('timestamp',))]


# --- FASE 5: tipo de cambio del dia guardado (BCCR oficial si hay token, si no implicito) ---

class CtlBccrTc(models.Model):
    """ctl_bccr_tc: TC CRC/USD del dia, consultado UNA vez en la manana y guardado.

    El MCP y la API leen de aca el resto del dia (no consultan la API del BCCR
    en cada pregunta). Fuente: 'BCCR oficial (SDDE 317/318)' via el paquete bccr,
    si no 'implicito_fuente' (mediana CRC/USD de la fuente) marcado como tal.
    """
    fecha = models.DateField(unique=True)
    tc_compra = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    tc_venta = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    fuente = models.TextField(blank=True, null=True)
    sobre = models.TextField(blank=True, null=True)
    corrida = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ctl_bccr_tc'
        ordering = ['-fecha']

