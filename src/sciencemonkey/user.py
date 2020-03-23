"""All the data for a sciencemonkey user."""

__all__ = [
    "User",
]

import json
import time
from dataclasses import dataclass
from string import Template

import jwt

from sciencemonkey.config import Configuration


@dataclass
class User:
    username: str
    uidnumber: int
    token: str

    def __init__(self, username, uidnumber):
        self.username = username
        self.uidnumber = uidnumber
        self.generate_token()

    def generate_token(self):
        with open("static/jwt-template.json", "r") as f:
            token_template = Template(f.read())

        with open(Configuration.private_key_path, "r") as f:
            signing_key = f.read()

        current_time = int(time.time())

        token_data = {
            "username": self.username,
            "uidnumber": self.uidnumber,
            "issue_time": current_time,
            "expiration_time": current_time + 2419200,
        }

        token_dict = json.loads(token_template.substitute(token_data))
        self.token = jwt.encode(
            token_dict,
            key=signing_key,
            headers={"kid": "reissuer"},
            algorithm="RS256",
        ).decode("utf-8")
