from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.firebase import db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sync")
async def sync_user(decoded_token: dict = Depends(get_current_user)):
    """Create or update the signed-in user's record in the 'accounts' collection."""
    uid = decoded_token["uid"]
    account = {
        "name": decoded_token.get("name"),
        "email": decoded_token.get("email"),
        "profile_image": decoded_token.get("picture"),
    }

    db.collection("accounts").document(uid).set(account, merge=True)
    return {"uid": uid, **account}


@router.get("/me")
async def get_me(decoded_token: dict = Depends(get_current_user)):
    doc = db.collection("accounts").document(decoded_token["uid"]).get()
    if not doc.exists:
        return {"uid": decoded_token["uid"], "name": None, "email": None, "profile_image": None}
    return {"uid": decoded_token["uid"], **doc.to_dict()}
