from fastapi import APIRouter, HTTPException
from google.auth.exceptions import RefreshError
from googleapiclient.http import MediaInMemoryUpload
from app.connectors.google.common import get_service

router = APIRouter(prefix="/drive", tags=["drive"])

@router.post("/createFolder")
def create_folder(payload: dict):
    name = (payload or {}).get("name")
    parent_id = (payload or {}).get("parentId")
    if not name:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "name is required"})
    try:
        service = get_service("drive", "v3")
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        folder = service.files().create(body=body, fields="id,name,parents").execute()
        return {"ok": True, "id": folder["id"], "name": folder["name"], "parents": folder.get("parents", [])}
    except (RefreshError, FileNotFoundError):
        raise HTTPException(status_code=401, detail={"ok": False, "error": "Google token missing/expired. Re-auth required."})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})

@router.post("/uploadText")
def upload_text(payload: dict):
    name = (payload or {}).get("name")
    content = (payload or {}).get("content", "")
    folder_id = (payload or {}).get("folderId")
    if not name:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "name is required"})
    try:
        service = get_service("drive", "v3")
        metadata = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain", resumable=False)
        file = service.files().create(body=metadata, media_body=media, fields="id,name,parents").execute()
        return {"ok": True, "id": file["id"], "name": file["name"], "parents": file.get("parents", [])}
    except (RefreshError, FileNotFoundError):
        raise HTTPException(status_code=401, detail={"ok": False, "error": "Google token missing/expired. Re-auth required."})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})
