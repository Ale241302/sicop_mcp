"""Serializers genericos para los modelos SICOP (mismo nombre de campo = columna fuente)."""
from django.conf import settings
from rest_framework import serializers

from sicop import models as m


class DynamicModelSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        model = self.Meta.model
        for field_name in self.fields:
            if getattr(model, field_name, None) is None:
                continue
            field_type = model._meta.get_field(field_name).get_internal_type()
            if field_type in ("DecimalField", "IntegerField", "BigIntegerField"):
                self.fields[field_name].allow_null = True
                self.fields[field_name].required = False


def make_serializer(model, name):
    meta = type("Meta", (), {"model": model, "fields": "__all__", "read_only_fields": ["id"]})
    return type(name + "Serializer", (DynamicModelSerializer,), {"Meta": meta})


def _mask_cedula(v):
    """Cédula parcial: conserva 3 + 2 dígitos (búsqueda dirigida sin exponerla)."""
    v = (v or "").strip()
    if len(v) <= 5:
        return "*" * len(v)
    return v[:3] + "*" * (len(v) - 5) + v[-2:]


def _inhibiciones_serializer(base):
    """Enmascara los datos personales salvo decisión expresa (Ley 8968)."""
    def to_representation(self, obj):
        data = base.to_representation(self, obj)
        if not getattr(settings, "SICOP_INHIBICIONES_NOMBRES", False):
            if data.get("NOM_FUNCIONARIO"):
                data["NOM_FUNCIONARIO"] = "DATO_PERSONAL_RESTRINGIDO"
            if data.get("CED_FUNCIONARIO"):
                data["CED_FUNCIONARIO"] = _mask_cedula(data["CED_FUNCIONARIO"])
        return data

    return type(base.__name__, (base,), {"to_representation": to_representation})


SERIALIZER_BY_MODEL = {}


def serializer_for(model):
    name = model.__name__
    if name not in SERIALIZER_BY_MODEL:
        ser = make_serializer(model, name)
        if name == "SicopInhibiciones":
            ser = _inhibiciones_serializer(ser)
        SERIALIZER_BY_MODEL[name] = ser
    return SERIALIZER_BY_MODEL[name]
