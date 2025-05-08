from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from auth_utils import hash_password, verify_password, create_access_token, verify_access_token
from config import get_db
from schemas.models import *
from datetime import timedelta

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user = db.query(UserInDB).filter(UserInDB.email == user.email).first()
        if not db_user or not verify_password(user.password, db_user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        access_token = create_access_token(
            data={"sub": user.email, "type": db_user.type},
            expires_delta=timedelta(minutes=30)
        )
        return {"access_token": access_token, "type": db_user.type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/register", response_model=Token)
def register(user: CreateUser, db: Session = Depends(get_db)):
    if db.query(UserInDB).filter(UserInDB.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user.password)
    new_user = UserInDB(email=user.email, hashed_password=hashed_password, name=user.name, type=user.type)
    db.add(new_user)
    db.commit()

    access_token = create_access_token(
        data={"sub": new_user.email, "type": new_user.type},
        expires_delta=timedelta(minutes=30)
    )
    return {"access_token": access_token, "type": new_user.type}

@router.delete("/users/", response_model=dict)
def delete_all_users(db: Session = Depends(get_db)):
    try:
        db.query(UserInDB).delete()
        db.commit()  
        return {"message": "All users deleted successfully."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/users/me")
def get_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("sub")
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.delete("/delete_all/")
def delete_all(db: Session = Depends(get_db)):
    try:
        db.query(ScoresInDB).delete()
        db.query(StudentInDB).delete()
        db.query(GradeInDB).delete()
        
        db.commit()  
        return {"message": "All users, grades, students, and scores deleted successfully."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))