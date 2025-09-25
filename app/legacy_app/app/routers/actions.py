# src/app/routers/actions.py
import base64, io, os
from googleapiclient.errors import HttpError
from fastapi import APIRouter, HTTPException, Query
import os, base64, io
from fastapi import APIRouter, HTTPException, Query
from ..connectors.google.common import get_drive_service, get_gmail_service
from email.message import EmailMessage
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

def _gql_escape(s: str) -> str:
    # Escape single quotes for Google Drive query strings
    return s.replace("'", "\\'")

router = APIRouter(prefix="/action", tags=["actions"])

import os
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/action", tags=["actions"])

def _check(key: str | None):
    expected = os.environ.get("PT_API_KEY") or ""
    if not expected:
        raise HTTPException(status_code=500, detail="Server missing PT_API_KEY")
    if key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/ping")
def ping(key: str = Query(...)):
    _check(key)
    return {"ok": True, "key_len": len(os.environ.get("PT_API_KEY") or "")}


def _b64url_decode(s: str) -> bytes:
    # tolerate missing padding in URL-safe base64
    s = s.strip()
    s += "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s.encode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

# --- uploadText handler ---
@router.get("/uploadTextByFolderName")
def upload_text_by_folder_name(
    key: str = Query(...),
    name: str = Query(...),
    folder: str = Query(...),
    content_b64: str = Query(...),
    create_if_missing: bool = True,
    share: bool = True,                 # <— NEW
    share_role: str = "reader",         # <— NEW: reader|writer|commenter
):
    _check(key)
    try:
        svc = get_drive_service()

        # find/create folder
        q = (
            f"name = '{_gql_escape(folder)}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        res = svc.files().list(q=q, pageSize=1, fields="files(id, name)").execute()
        files = res.get("files", [])
        if not files:
            if not create_if_missing:
                raise HTTPException(status_code=404, detail=f"Folder not found: {folder}")
            folder_meta = svc.files().create(
                body={"name": folder, "mimeType": "application/vnd.google-apps.folder"},
                fields="id, name",
            ).execute()
        else:
            folder_meta = files[0]

        # upload text
        content = _b64url_decode(content_b64)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
        body = {"name": name, "parents": [folder_meta["id"]]}
        created = svc.files().create(
            body=body, media_body=media, fields="id, name, webViewLink, parents"
        ).execute()

        # optional share
        if share:
            svc.permissions().create(
                fileId=created["id"],
                body={"type": "anyone", "role": share_role},
                sendNotificationEmail=False,
            ).execute()
            created = svc.files().get(
                fileId=created["id"], fields="id, name, webViewLink, webContentLink, parents"
            ).execute()

        return {"folder": folder_meta, "file": created}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/uploadText")
def upload_text(
    key: str = Query(...),
    name: str = Query(...),
    content_b64: str = Query(...),
    folderId: str | None = None,
    share: bool = False,               # default off here
    share_role: str = "reader",
):
    _check(key)
    try:
        service = get_drive_service()
        content = _b64url_decode(content_b64)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
        body = {"name": name}
        if folderId:
            body["parents"] = [folderId]
        created = service.files().create(
            body=body, media_body=media, fields="id, name, webViewLink, parents"
        ).execute()
        if share:
            service.permissions().create(
                fileId=created["id"],
                body={"type": "anyone", "role": share_role},
                sendNotificationEmail=False,
            ).execute()
            created = service.files().get(
                fileId=created["id"], fields="id, name, webViewLink, webContentLink, parents"
            ).execute()
        return created
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- NEW: share (anyone with link, reader) ---
@router.get("/share")
def share_anyone(
    key: str = Query(...),
    fileId: str = Query(...),
    role: str = Query("reader"),
):
    _check(key)
    try:
        svc = get_drive_service()
        # create/overwrite a public link permission
        svc.permissions().create(
            fileId=fileId,
            body={"type": "anyone", "role": role},
            sendNotificationEmail=False,
        ).execute()
        meta = svc.files().get(
            fileId=fileId, fields="id, name, webViewLink, webContentLink"
        ).execute()
        return meta
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- email handler ---
@router.get("/email")
def email(
    key: str = Query(...),
    to: str = Query(...),
    subject: str = Query(""),
    body_b64: str = Query(""),
):
    _check(key)
    try:
        service = get_gmail_service()
        import email.message as em

        msg = em.EmailMessage()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject
        if body_b64:
            msg.set_content(_b64url_decode(body_b64).decode("utf-8", errors="ignore"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        res = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": res.get("id")}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from email.message import EmailMessage
from googleapiclient.http import MediaIoBaseDownload

@router.get("/emailFromDrive")
def email_from_drive(
    key: str = Query(...),
    fileId: str = Query(...),
    to: str = Query(...),
    subject: str = Query(""),
    mode: str = Query("inline"),           # "inline" or "attach"
    export_mime: str | None = None,        # for Google Docs export; defaults based on mode
):
    """
    Email a Drive file by ID.
    - Google Docs/Sheets/Slides: uses files().export (text/plain for inline, application/pdf for attach by default)
    - Other files: downloads; inline if text/*, else attach
    """
    _check(key)
    try:
        dsvc = get_drive_service()
        gsvc = get_gmail_service()

        meta = dsvc.files().get(fileId=fileId, fields="id, name, mimeType").execute()
        name = meta.get("name", "file")
        mime = meta.get("mimeType", "application/octet-stream")

        text_body: str | None = None
        attach_bytes: bytes | None = None
        attach_mime: str | None = None
        attach_name: str | None = None

        def _download_file() -> bytes:
            buf = io.BytesIO()
            req = dsvc.files().get_media(fileId=fileId)
            downloader = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            return buf.getvalue()

        def _ext_for(m: str) -> str:
            mapping = {
                "application/pdf": ".pdf",
                "text/plain": ".txt",
                "text/markdown": ".md",
                "text/csv": ".csv",
            }
            return mapping.get(m, "")

        if mime.startswith("application/vnd.google-apps."):
            # Google Workspace file
            if mode == "inline":
                emime = export_mime or "text/plain"
            else:
                emime = export_mime or "application/pdf"
            data = dsvc.files().export(fileId=fileId, mimeType=emime).execute()
            attach_bytes = data if isinstance(data, (bytes, bytearray)) else bytes(data)
            attach_mime = emime
            attach_name = name + _ext_for(emime)

            if mode == "inline" and emime.startswith("text/"):
                # inline as email body
                text_body = attach_bytes.decode("utf-8", errors="ignore")
                attach_bytes = None
                attach_mime = None
                attach_name = None
        else:
            # Regular file
            if mode == "inline" and mime.startswith("text/"):
                text_body = _download_file().decode("utf-8", errors="ignore")
            else:
                attach_bytes = _download_file()
                attach_mime = mime
                attach_name = name

        # Build email
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject or f"File: {name}"

        if text_body:
            msg.set_content(text_body)
        else:
            msg.set_content(f"See attached: {attach_name or name}")
            if attach_bytes is not None and attach_mime:
                maintype, subtype = (attach_mime.split("/", 1) + ["octet-stream"])[:2]
                msg.add_attachment(attach_bytes, maintype=maintype, subtype=subtype, filename=attach_name or name)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        res = gsvc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": res.get("id"), "file": {"id": fileId, "name": name, "mimeType": mime}}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from email.message import EmailMessage
def _gql_escape(s: str) -> str:
    return s.replace("'", "\\'")

def _b64url_decode(s: str) -> bytes:
    s = s.strip(); s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("utf-8"))
@router.get("/upsertAndMailLinkByFolderName")
def upsert_and_mail_link_by_folder_name(
    key: str = Query(...),
    folder: str = Query(...),
    name: str = Query(...),
    content_b64: str = Query(...),
    share: bool = True,
    to: str = Query(...),
    subject: str = Query(""),
    share_role: str = "reader",
):
    _check(key)
    try:
        dsvc = get_drive_service()
        gsvc = get_gmail_service()
        # 1) find/create folder
        q = (
            f"name = '{_gql_escape(folder)}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        res = dsvc.files().list(q=q, pageSize=1, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            folder_meta = files[0]
        else:
            folder_meta = dsvc.files().create(
                body={"name": folder, "mimeType": "application/vnd.google-apps.folder"},
                fields="id, name",
            ).execute()
        folder_id = folder_meta["id"]

        # 2) upsert by name within folder
        q2 = (
            f"name = '{_gql_escape(name)}' and '{folder_id}' in parents and trashed = false"
        )
        ex = dsvc.files().list(q=q2, pageSize=1, fields="files(id, name)").execute().get("files", [])
        content = _b64url_decode(content_b64)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
        if ex:
            file_id = ex[0]["id"]
            updated = dsvc.files().update(
                fileId=file_id,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()
            created = updated
        else:
            created = dsvc.files().create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()

        # 3) share (optional)
        if share:
            dsvc.permissions().create(
                fileId=created["id"],
                body={"type": "anyone", "role": share_role},
                sendNotificationEmail=False,
            ).execute()
            created = dsvc.files().get(
                fileId=created["id"],
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()

        # 4) email the link
        link = created.get("webViewLink") or created.get("webContentLink") or "(no link)"
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject or f"Link: {created['name']}"
        msg.set_content(f"Here is your file link:\n{link}\n\nFile ID: {created['id']}")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        sent = gsvc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"folder": folder_meta, "file": created, "email": {"id": sent.get("id")}}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upsertAndMailLinkByFolderName")
def upsert_and_mail_link_by_folder_name(
    key: str = Query(...),
    folder: str = Query(...),
    name: str = Query(...),
    content_b64: str = Query(...),
    share: bool = True,
    to: str = Query(...),
    subject: str = Query(""),
    share_role: str = "reader",
):
    _check(key)
    try:
        dsvc = get_drive_service()
        gsvc = get_gmail_service()

        # 1) find/create folder
        q = (
            f"name = '{_gql_escape(folder)}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        res = dsvc.files().list(q=q, pageSize=1, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            folder_meta = files[0]
        else:
            folder_meta = dsvc.files().create(
                body={"name": folder, "mimeType": "application/vnd.google-apps.folder"},
                fields="id, name",
            ).execute()
        folder_id = folder_meta["id"]

        # 2) upsert by name within folder
        q2 = f"name = '{_gql_escape(name)}' and '{folder_id}' in parents and trashed = false"
        ex = dsvc.files().list(q=q2, pageSize=1, fields="files(id, name)").execute().get("files", [])
        content = _b64url_decode(content_b64)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
        if ex:
            file_id = ex[0]["id"]
            created = dsvc.files().update(
                fileId=file_id, media_body=media,
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()
        else:
            created = dsvc.files().create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()

        # 3) share (optional)
        if share:
            dsvc.permissions().create(
                fileId=created["id"],
                body={"type": "anyone", "role": share_role},
                sendNotificationEmail=False,
            ).execute()
            created = dsvc.files().get(
                fileId=created["id"],
                fields="id, name, webViewLink, webContentLink, parents",
            ).execute()

        # 4) email the link
        link = created.get("webViewLink") or created.get("webContentLink") or "(no link)"
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject or f"Link: {created['name']}"
        msg.set_content(f"Here is your file link:\n{link}\n\nFile ID: {created['id']}")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        sent = gsvc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"folder": folder_meta, "file": created, "email": {"id": sent.get("id")}}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/emailFromDriveByFolderName")
def email_from_drive_by_folder_name(
    key: str = Query(...),
    folder: str = Query(...),
    name: str = Query(...),
    to: str = Query(...),
    subject: str = Query(""),
    mode: str = Query("inline"),           # "inline" or "attach"
    export_mime: str | None = None,        # optional override for Google files
):
    """
    Find <name> inside folder <folder> and email it (inline for text, else attach).
    If it's a Google Doc/Sheet/Slide, export (text/plain for inline, PDF for attach by default).
    Picks the most recently modified match if duplicates exist.
    """
    _check(key)
    try:
        dsvc = get_drive_service()
        gsvc = get_gmail_service()

        # 1) find folder by exact name
        q_folder = (
            f"name = '{_gql_escape(folder)}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        f_res = dsvc.files().list(q=q_folder, pageSize=1, fields="files(id,name)").execute()
        folders = f_res.get("files", [])
        if not folders:
            raise HTTPException(status_code=404, detail=f"Folder not found: {folder}")
        folder_id = folders[0]["id"]

        # 2) find file (most recent if multiple)
        q_file = f"name = '{_gql_escape(name)}' and '{folder_id}' in parents and trashed = false"
        flist = dsvc.files().list(
            q=q_file,
            orderBy="modifiedTime desc",
            pageSize=1,
            fields="files(id,name,mimeType,modifiedTime)"
        ).execute().get("files", [])
        if not flist:
            raise HTTPException(status_code=404, detail=f"File not found in folder: {name}")
        meta = flist[0]
        file_id = meta["id"]
        mime = meta.get("mimeType", "application/octet-stream")
        fname = meta.get("name", "file")

        # Helpers
        def _download_bytes() -> bytes:
            buf = io.BytesIO()
            req = dsvc.files().get_media(fileId=file_id)
            dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()

        def _ext_for(m: str) -> str:
            return {
                "application/pdf": ".pdf",
                "text/plain": ".txt",
                "text/markdown": ".md",
                "text/csv": ".csv",
            }.get(m, "")

        # 3) prepare email content / attachment
        text_body: str | None = None
        attach_bytes: bytes | None = None
        attach_mime: str | None = None
        attach_name: str | None = None

        if mime.startswith("application/vnd.google-apps."):
            # Google Workspace file → export
            if mode == "inline":
                emime = export_mime or "text/plain"
            else:
                emime = export_mime or "application/pdf"
            data = dsvc.files().export(fileId=file_id, mimeType=emime).execute()
            blob = data if isinstance(data, (bytes, bytearray)) else bytes(data)
            if mode == "inline" and emime.startswith("text/"):
                text_body = blob.decode("utf-8", errors="ignore")
            else:
                attach_bytes, attach_mime = blob, emime
                attach_name = fname + _ext_for(emime)
        else:
            # Regular file
            if mode == "inline" and mime.startswith("text/"):
                text_body = _download_bytes().decode("utf-8", errors="ignore")
            else:
                attach_bytes = _download_bytes()
                attach_mime = mime
                attach_name = fname

        # 4) build + send email
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject or f"File: {fname}"
        if text_body:
            msg.set_content(text_body)
        else:
            msg.set_content(f"See attached: {attach_name or fname}")
            if attach_bytes is not None and attach_mime:
                maintype, subtype = (attach_mime.split("/", 1) + ["octet-stream"])[:2]
                msg.add_attachment(attach_bytes, maintype=maintype, subtype=subtype, filename=attach_name or fname)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        sent = gsvc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"email": {"id": sent.get("id")}, "file": {"id": file_id, "name": fname, "mimeType": mime}}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # --- EMAIL FROM DRIVE BY FILE ID ---
from fastapi import Query
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from ..connectors.google.common import get_drive_service, get_gmail_service
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import io, mimetypes

@router.get("/emailFromDriveByFileId", tags=["action"])
def email_from_drive_by_file_id(
    fileId: str = Query(..., description="Drive fileId"),
    to: str = Query(..., description="Recipient email"),
    subject: str = Query("Drive File"),
    body: str = Query("Attached file from Drive."),
    mode: str = Query("attachment", regex="^(attachment|inline)$"),
):
    """
    Fetch a Drive file by fileId and email it via Gmail.
    - Supports Google Docs/Sheets/Slides via automatic PDF export.
    - mode: 'attachment' (default) or 'inline' content-disposition.
    """
    try:
        drive = get_drive_service()
        gmail = get_gmail_service()

        # 1) Get metadata
        meta = drive.files().get(fileId=fileId, fields="id,name,mimeType").execute()
        if not meta:
            raise HTTPException(status_code=404, detail=f"File not found for id: {fileId}")

        name = meta.get("name") or "file"
        mime = meta.get("mimeType") or "application/octet-stream"

        # 2) Download content (export Google types as PDF)
        buf = io.BytesIO()
        if mime.startswith("application/vnd.google-apps."):
            export_map = {
                "application/vnd.google-apps.document": "application/pdf",
                "application/vnd.google-apps.spreadsheet": "application/pdf",
                "application/vnd.google-apps.presentation": "application/pdf",
            }
            export_mime = export_map.get(mime, "application/pdf")
            req = drive.files().export_media(fileId=fileId, mimeType=export_mime)
            filename = name if name.lower().endswith(".pdf") else f"{name}.pdf"
            content_type = export_mime
        else:
            req = drive.files().get_media(fileId=fileId)
            filename = name
            content_type = mime or (mimetypes.guess_type(filename)[0] or "application/octet-stream")

        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        data = buf.read()

        # 3) Build email
        msg = MIMEMultipart()
        msg["to"] = to
        msg["subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        maintype, subtype = (content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream"))
        part = MIMEBase(maintype, subtype)
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Type", content_type)
        part.add_header("Content-Disposition", f'{mode}; filename="{filename}"')
        msg.attach(part)

        raw = encoders._bencode(msg.as_bytes()).decode("utf-8")  # base64url for Gmail
        gmail.users().messages().send(userId="me", body={"raw": raw}).execute()

        return {"status": "sent", "to": to, "fileId": fileId, "filename": filename, "contentType": content_type}
    except HttpError as e:
        raise HTTPException(status_code=e.resp.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
# --- END EMAIL FROM DRIVE BY FILE ID ---

