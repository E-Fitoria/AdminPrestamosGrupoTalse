from email.mime.text import MIMEText
from pathlib import Path
import base64
import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
_BASE = Path(__file__).resolve().parent
_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_PATH", str(_BASE / "credentials.json"))
_TOKEN_FILE = os.getenv("GMAIL_TOKEN_PATH", str(_BASE / "token_gmail_v1.pickle"))

def _obtener_credenciales():
    creds = None
    b64 = os.getenv("GMAIL_TOKEN_B64")
    if b64:
        creds = pickle.loads(base64.b64decode(b64))
    elif os.path.exists(_TOKEN_FILE):
        with open(_TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if not b64:
            with open(_TOKEN_FILE, "wb") as token:
                pickle.dump(creds, token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(_TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
    return creds


def send_mail_google(correoColaborador, Nombres, Cedula, Password):
    # nombre de la api, version, credenciales
    service = build("gmail", "v1", credentials=_obtener_credenciales())

    # cuerpo del mensaje (Cedula se incluye para que el colaborador sepa con que ingresar)
    cuerpo = (
        "ESTE ES UN MENSAJE AUTOMATICO\n"
        f"Hola: {Nombres}\n"
        "Bienvenido al sistema de préstamos de GrupoTalse\n"
        "Sus credenciales por defecto para acceder al sistema:\n"
        f"Cédula / usuario de referencia: {Cedula}\n"
        f"Contraseña: {Password}\n\n"
        "NOTA: AL INGRESAR AL SISTEMA PUEDE CAMBIAR SU CONTRASEÑA POR DEFECTO "
        "POR UNA CONTRASEÑA DE SU PREFERENCIA"
    )
    message = MIMEText(cuerpo)
    message["to"] = correoColaborador
    message["subject"] = "Registrado"

    # Codificar el mensaje en base64; Gmail no acepta texto plano crudo en el envio
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw_message}

    try:
        service.users().messages().send(userId="me", body=body).execute()
        print("Mensaje enviado")
    except HttpError as error:
        print(f"Error: {error}")
