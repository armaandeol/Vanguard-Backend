from pydantic import BaseModel


class UserAccount(BaseModel):
    uid: str
    name: str | None = None
    email: str | None = None
    profile_image: str | None = None
