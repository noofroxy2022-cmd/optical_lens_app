"""نسخ احتياطي محلي لقاعدة البيانات (SQLite) - عرض / نسخ الآن / تعليمات استرجاع.

الاسترجاع لا يُنفَّذ من خلال الخادم أثناء عمله: استبدال ملف SQLite الحيّ وحذف
ملفات ‎-wal / -shm‎ بينما قد تحتفظ SQLAlchemy باتصالات مفتوحة غير آمن للإنتاج.
نقطة النهاية أدناه تُرجع خطوات الاسترجاع اليدوي دون اتصال فقط ولا تُعدّل أي ملف.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import backup_service

router = APIRouter(prefix="/backup", tags=["النسخ الاحتياطي"])


class RestoreRequest(BaseModel):
    name: str


@router.get("/")
def get_backups():
    return {
        "is_sqlite": backup_service.is_sqlite(),
        "backup_dir": backup_service.backup_dir() if backup_service.is_sqlite() else None,
        "keep": backup_service.KEEP,
        "backups": backup_service.list_backups() if backup_service.is_sqlite() else [],
    }


@router.post("/now")
def backup_now():
    if not backup_service.is_sqlite():
        raise HTTPException(status_code=400, detail="النسخ الاحتياطي التلقائي يدعم SQLite فقط")
    try:
        info = backup_service.create_backup(reason="manual")
        removed = backup_service.rotate()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل إنشاء النسخة: {e}")
    return {"success": True, "backup": info, "rotated_out": removed,
            "backups": backup_service.list_backups()}


@router.post("/restore")
def restore(req: RestoreRequest):
    """Returns the manual OFFLINE restore steps for the chosen snapshot. Does
    NOT replace the live database - restore is performed with the server
    stopped (see module docstring)."""
    if not backup_service.is_sqlite():
        raise HTTPException(status_code=400, detail="الاسترجاع يدعم SQLite فقط")
    try:
        result = backup_service.restore_instructions(req.name)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=f"نسخة غير صالحة: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"تعذّر التحقق من النسخة: {e}")
    # 200 with performed=False - informational, no live-DB mutation happened.
    return {"success": True, **result}
