from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum


def db_enum(enum_cls: type[PyEnum], *, name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
    )
