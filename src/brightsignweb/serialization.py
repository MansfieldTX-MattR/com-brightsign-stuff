from __future__ import annotations
from typing import Iterator
import dataclasses
import datetime

import jsonfactory

class DataclassSerialize:
    def _iter_ser_fields(self) -> Iterator[str]:
        for f in dataclasses.fields(self):
            yield f.name

    def _serialize(self) -> dict:
        return {attr:getattr(self, attr) for attr in self._iter_ser_fields()}

    @classmethod
    def _get_deserialize_kwargs(cls, data: dict) -> dict:
        return data

    @classmethod
    def _deserialize(cls, data: dict):
        kw = cls._get_deserialize_kwargs(data)
        return cls(**kw)


@jsonfactory.register
class JsonEncoder:
    CLASSES = (DataclassSerialize, datetime.datetime, datetime.timedelta)
    def cls_to_str(self, cls):
        return '.'.join([cls.__module__, cls.__qualname__])

    def str_to_cls(self, s):
        def iter_subcls(cls):
            yield cls
            for subcls in cls.__subclasses__():
                yield from iter_subcls(subcls)
        if '.' not in s:
            return None
        clsname = s.split('.')[-1]
        modname = '.'.join(s.split('.')[:-1])
        for cls in self.CLASSES:
            for subcls in iter_subcls(cls):
                if subcls.__module__ != modname:
                    continue
                if subcls.__qualname__ != clsname:
                    continue
                return subcls

    def encode(self, o):
        d = None
        if isinstance(o, datetime.datetime):
            d = {'timestamp':o.timestamp(), '__class__':self.cls_to_str(o.__class__)}
        elif isinstance(o, datetime.timedelta):
            d = {'total_seconds':o.total_seconds(), '__class__':self.cls_to_str(o.__class__)}
        elif isinstance(o, DataclassSerialize):
            d = o._serialize()
            d['__class__'] = self.cls_to_str(o.__class__)
        return d

    def decode(self, d):
        if '__class__' in d:
            cls = self.str_to_cls(d['__class__'])
            if cls is not None:
                if cls is datetime.datetime:
                    return datetime.datetime.fromtimestamp(d['timestamp'])
                elif cls is datetime.timedelta:
                    return datetime.timedelta(seconds=d['total_seconds'])
                elif issubclass(cls, DataclassSerialize):
                    d = d.copy()
                    del d['__class__']
                    return cls._deserialize(d)
        return d
