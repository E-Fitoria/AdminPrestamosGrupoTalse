from dotenv import load_dotenv
import os
from passlib.context import CryptContext 

load_dotenv()

class FlaskConfig:
    FLASK_APP = os.getenv('FLASK_APP')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG')
    SECRET_KEY = os.getenv('SecretKey')

class DatabaseConfig:
    DATABASE_URL = os.getenv('DATABASE_URL')

class PasslibConfig:
    CONTEXT = CryptContext(
        schemes=["pbkdf2_sha256"],
        default="pbkdf2_sha256",
        pbkdf2_sha256__default_rounds=30000
    )