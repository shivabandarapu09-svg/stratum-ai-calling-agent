from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db, hash_password
from app.models import User, Organization
from app.schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    pwd_hash = hash_password(req.password)
    user = db.query(User).filter(User.email == req.email, User.hashed_password == pwd_hash).first()
    if not user:
        # For simple demo convenience, if admin user, match or auto-validate
        if req.email == "admin@voicebharat.ai" and req.password == "admin123":
            user = db.query(User).filter(User.email == req.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    org = user.organization
    return TokenResponse(
        access_token=f"token-{user.id}",
        user_name=user.full_name or "Admin User",
        organization_id=org.id,
        organization_name=org.name
    )

@router.get("/me", response_model=UserOut)
def get_current_user(db: Session = Depends(get_db)):
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
