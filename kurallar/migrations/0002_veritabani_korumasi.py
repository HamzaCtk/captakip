"""Kural sürümleri, parametreleri ve değerlendirmeleri veritabanı seviyesinde korunur.

- Parametre ve değerlendirme: UPDATE ve DELETE yasak.
- Kural sürümü: yalnızca yürürlük bitişi işlenebilir; diğer alanlar değişmez, silinemez.
- Uyarı: durum değişebilir (görüldü/kapatıldı) ama silinemez.
"""
from django.db import migrations

TAM_KORUMA = ["kurallar_kuralparametresi", "kurallar_kuraldegerlendirmesi"]
SURUM = "kurallar_kuralsurumu"
SURUM_SABIT = "program_turu, ad, dayanak, yururluk_baslangic, olusturan_id, zaman"
SILME_YASAK = [SURUM, "kurallar_uyari"]


def _sqlite_kur():
    k = []
    for t in TAM_KORUMA:
        k.append(f"CREATE TRIGGER IF NOT EXISTS {t}_guncelleme_yasak BEFORE UPDATE ON {t} "
                 f"BEGIN SELECT RAISE(ABORT, 'Kayit degistirilemez'); END;")
    for t in TAM_KORUMA + SILME_YASAK:
        k.append(f"CREATE TRIGGER IF NOT EXISTS {t}_silme_yasak BEFORE DELETE ON {t} "
                 f"BEGIN SELECT RAISE(ABORT, 'Kayit silinemez'); END;")
    k.append(f"CREATE TRIGGER IF NOT EXISTS {SURUM}_guncelleme_yasak BEFORE UPDATE OF {SURUM_SABIT} ON {SURUM} "
             f"BEGIN SELECT RAISE(ABORT, 'Kural surumu degistirilemez'); END;")
    return k


def _sqlite_kaldir():
    k = [f"DROP TRIGGER IF EXISTS {t}_guncelleme_yasak;" for t in TAM_KORUMA + [SURUM]]
    k += [f"DROP TRIGGER IF EXISTS {t}_silme_yasak;" for t in TAM_KORUMA + SILME_YASAK]
    return k


def _pg_kur():
    k = ["""CREATE OR REPLACE FUNCTION kurallar_koruma() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Kural kaydi degistirilemez/silinemez'; END;
            $$ LANGUAGE plpgsql;"""]
    for t in TAM_KORUMA:
        k.append(f"CREATE TRIGGER {t}_koruma BEFORE UPDATE OR DELETE ON {t} "
                 f"FOR EACH ROW EXECUTE FUNCTION kurallar_koruma();")
    for t in SILME_YASAK:
        k.append(f"CREATE TRIGGER {t}_silme BEFORE DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION kurallar_koruma();")
    k.append(f"CREATE TRIGGER {SURUM}_guncelleme BEFORE UPDATE OF {SURUM_SABIT} ON {SURUM} "
             f"FOR EACH ROW EXECUTE FUNCTION kurallar_koruma();")
    return k


def _pg_kaldir():
    k = [f"DROP TRIGGER IF EXISTS {t}_koruma ON {t};" for t in TAM_KORUMA]
    k += [f"DROP TRIGGER IF EXISTS {t}_silme ON {t};" for t in SILME_YASAK]
    k += [f"DROP TRIGGER IF EXISTS {SURUM}_guncelleme ON {SURUM};", "DROP FUNCTION IF EXISTS kurallar_koruma();"]
    return k


def _calistir(sozluk):
    def fn(apps, schema_editor):
        for sql in sozluk.get(schema_editor.connection.vendor, lambda: [])():
            schema_editor.execute(sql)
    return fn


class Migration(migrations.Migration):
    dependencies = [("kurallar", "0001_initial")]

    operations = [
        migrations.RunPython(
            _calistir({"sqlite": _sqlite_kur, "postgresql": _pg_kur}),
            _calistir({"sqlite": _sqlite_kaldir, "postgresql": _pg_kaldir}),
        ),
    ]
