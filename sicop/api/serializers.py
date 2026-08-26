"""Serializers genericos para los modelos SICOP (mismo nombre de campo = columna fuente)."""
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


SERIALIZER_BY_MODEL = {}


def serializer_for(model):
    name = model.__name__
    if name not in SERIALIZER_BY_MODEL:
        SERIALIZER_BY_MODEL[name] = make_serializer(model, name)
    return SERIALIZER_BY_MODEL[name]
