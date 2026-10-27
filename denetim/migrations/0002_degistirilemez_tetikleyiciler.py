"""İşlem kaydı tablosunu veritabanı seviyesinde değiştirilemez yapar.

Python kodu atlatılsa bile (ör. doğrudan SQL ile) UPDATE ve DELETE
komutları veritabanı tarafından reddedilir.
"""
from django.db import migrations

TABLO = "denetim_islemkaydi"

SQLITE_KUR = [
    f"""CREATE TRIGGER IF NOT EXISTS {TABLO}_guncelleme_yasak
        BEFORE UPDATE ON {TABLO}
        BEGIN SELECT RAISE(ABORT, 'Islem kaydi degistirilemez'); END;""",
    f"""CREATE TRIGGER IF NOT EXISTS {TABLO}_silme_yasak
        BEFORE DELETE ON {TABLO}
        BEGIN SELECT RAISE(ABORT, 'Islem kaydi silinemez'); END;""",
]
SQLITE_KALDIR = [
    f"DROP TRIGGER IF EXISTS {TABLO}_guncelleme_yasak;",
    f"DROP TRIGGER IF EXISTS {TABLO}_silme_yasak;",
]

POSTGRES_KUR = [
    """CREATE OR REPLACE FUNCTION islemkaydi_degistirilemez() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'Islem kaydi degistirilemez/silinemez'; END;
       $$ LANGUAGE plpgsql;""",
    f"""CREATE TRIGGER {TABLO}_koruma
        BEFORE UPDATE OR DELETE ON {TABLO}
        FOR EACH ROW EXECUTE FUNCTION islemkaydi_degistirilemez();""",
]
POSTGRES_KALDIR = [
    f"DROP TRIGGER IF EXISTS {TABLO}_koruma ON {TABLO};",
    "DROP FUNCTION IF EXISTS islemkaydi_degistirilemez();",
]


def _calistir(komutlar_sozlugu):
    def fn(apps, schema_editor):
        komutlar = komutlar_sozlugu.get(schema_editor.connection.vendor, [])
        for sql in komutlar:
            schema_editor.execute(sql)
    return fn


class Migration(migrations.Migration):
    dependencies = [("denetim", "0001_initial")]

    operations = [
        migrations.RunPython(
            _calistir({"sqlite": SQLITE_KUR, "postgresql": POSTGRES_KUR}),
            _calistir({"sqlite": SQLITE_KALDIR, "postgresql": POSTGRES_KALDIR}),
        ),
    ]
