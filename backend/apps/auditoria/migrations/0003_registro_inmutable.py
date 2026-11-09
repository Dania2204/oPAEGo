"""RNF-12: la base de datos rechaza UPDATE y DELETE sobre el registro de auditoría.

Se implementa para PostgreSQL (motor de referencia) y SQLite (pruebas); en
otros motores la protección queda a nivel de aplicación (modelo y queryset).
"""

from django.db import migrations

TABLA = "auditoria_registroauditoria"

POSTGRES_CREAR = f"""
CREATE OR REPLACE FUNCTION paego_auditoria_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'El registro de auditoria es inmutable (RNF-12)';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER paego_auditoria_sin_update BEFORE UPDATE ON {TABLA}
    FOR EACH ROW EXECUTE FUNCTION paego_auditoria_inmutable();
CREATE TRIGGER paego_auditoria_sin_delete BEFORE DELETE ON {TABLA}
    FOR EACH ROW EXECUTE FUNCTION paego_auditoria_inmutable();
"""

POSTGRES_BORRAR = f"""
DROP TRIGGER IF EXISTS paego_auditoria_sin_update ON {TABLA};
DROP TRIGGER IF EXISTS paego_auditoria_sin_delete ON {TABLA};
DROP FUNCTION IF EXISTS paego_auditoria_inmutable();
"""

SQLITE_CREAR = [
    f"""CREATE TRIGGER paego_auditoria_sin_update BEFORE UPDATE ON {TABLA}
    BEGIN SELECT RAISE(ABORT, 'El registro de auditoria es inmutable (RNF-12)'); END;""",
    f"""CREATE TRIGGER paego_auditoria_sin_delete BEFORE DELETE ON {TABLA}
    BEGIN SELECT RAISE(ABORT, 'El registro de auditoria es inmutable (RNF-12)'); END;""",
]

SQLITE_BORRAR = [
    "DROP TRIGGER IF EXISTS paego_auditoria_sin_update;",
    "DROP TRIGGER IF EXISTS paego_auditoria_sin_delete;",
]


def crear(apps, schema_editor):
    motor = schema_editor.connection.vendor
    if motor == "postgresql":
        schema_editor.execute(POSTGRES_CREAR)
    elif motor == "sqlite":
        for sentencia in SQLITE_CREAR:
            schema_editor.execute(sentencia)


def borrar(apps, schema_editor):
    motor = schema_editor.connection.vendor
    if motor == "postgresql":
        schema_editor.execute(POSTGRES_BORRAR)
    elif motor == "sqlite":
        for sentencia in SQLITE_BORRAR:
            schema_editor.execute(sentencia)


class Migration(migrations.Migration):
    dependencies = [("auditoria", "0002_initial")]

    operations = [migrations.RunPython(crear, borrar)]
