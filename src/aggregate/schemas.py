"""Pydantic models: API responses now, connector contracts in later steps."""

from typing import Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    """The one shape every error response uses."""

    error: ErrorDetail


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
