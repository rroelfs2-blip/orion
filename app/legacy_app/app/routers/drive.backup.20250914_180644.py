# File: backend/app/legacy_app/app/routers/drive.py
from typing import Optional, Dict, Any
import io, base64

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from googleapiclient.http import MediaIoBaseUpload
from ..connectors.google.common import get_drive_service

router = APIRouter(prefix="/drive", tags=["google-drive"])

def _svc():
    try:
        return get_drive_service()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive auth failure: {e}")

def _escape_single_quotes(s: str) -> str:
    # Google Drive query uses single quotes; escape embedded ones
    return s.replace("'", "\\'")

def _ensure_folder(name: str, parent_id: Optional[str] = None) -> str:
    svc = _svc()
    q = (
        f"name = '{_escape_single_quotes(name)}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"
    resp = svc.files().list(q=q, spaces="drive", fields="files(id,name)").execute()
    if resp.get("files"):
        return resp["files"][0]["id"]
    meta: Dict[str, Any] = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    created = svc.files().create(body=meta, fields="id").execute()
    return created["id"]

@router.get("/ping")
def ping():
    return {"ok": True}

@router.get("/list")
def list_files(folderId: Optional[str] = Query(None)):
    svc = _svc()
    q = "trashed = false"
    if folderId:
        q = f"'{folderId}' in parents and trashed = false"
    resp = svc.files().list(
        q=q, pageSize=100, fields="files(id,name,mimeType,parents,modifiedTime,size,webViewLink)"
    ).execute()
    return {"files": resp.get("files", [])}

@router.get("/get")
def get_file(fileId: str = Query(...)):
    svc = _svc()
    meta = svc.files().get(
        fileId=fileId,
        fields="id,name,mimeType,parents,modifiedTime,size,webViewLink,webContentLink",
    ).execute()
    return meta

@router.get("/download")
def download(fileId: str = Query(...)):
    svc = _svc()
    data = svc.files().get_media(fileId=fileId).execute()
    meta = svc.files().get(fileId=fileId, fields="name").execute()
    filename = meta.get("name", "download.bin")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/createFolder")
def create_folder(
    name: str = Body(..., embed=True),
    parentId: Optional[str] = Body(None, embed=True),
):
    fid = _ensure_folder(name, parentId)
    return {"id": fid, "name": name, "parentId": parentId}

@router.post("/uploadText")
def upload_text(
    name: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
    folderId: Optional[str] = Body(None, embed=True),
):
    svc = _svc()
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain", resumable=False)
    meta: Dict[str, Any] = {"name": name}
    if folderId:
        meta["parents"] = [folderId]
    created = svc.files().create(body=meta, media_body=media, fields="id,name").execute()
    return {"id": created["id"], "name": created["name"]}

@router.post("/uploadFile")
def upload_file(
    name: str = Body(..., embed=True),
    content_base64: str = Body(..., embed=True),
    mimeType: str = Body("application/octet-stream", embed=True),
    folderId: Optional[str] = Body(None, embed=True),
):
    svc = _svc()
    raw = base64.b64decode(content_base64)
    media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=mimeType, resumable=False)
    meta: Dict[str, Any] = {"name": name}
    if folderId:
        meta["parents"] = [folderId]
    created = svc.files().create(body=meta, media_body=media, fields="id,name").execute()
    return {"id": created["id"], "name": created["name"]}

@router.post("/delete")
def delete_file(fileId: str = Body(..., embed=True)):
    svc = _svc()
    svc.files().delete(fileId=fileId).execute()
    return {"ok": True, "deleted": fileId}

@router.post("/search")
def search(q: str = Body(..., embed=True)):
    svc = _svc()
    resp = svc.files().list(q=q, fields="files(id,name,mimeType,parents,modifiedTime,size,webViewLink)").execute()
    return {"files": resp.get("files", [])}

@router.post("/findOrCreateFolderByName")
def find_or_create(name: str = Body(..., embed=True), parentId: Optional[str] = Body(None, embed=True)):
    fid = _ensure_folder(name, parentId)
    return {"id": fid, "name": name, "parentId": parentId}
