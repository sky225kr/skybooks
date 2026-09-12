import os
import json
import base64
import secrets
import threading
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext

app = FastAPI()

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://skybooks-sepia.vercel.app",  # 프론트엔드 배포 주소 추가
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.json"
db_lock = threading.Lock()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_EMAILS = ["yooneeo@gmail.com"]

SESSION_TTL = timedelta(hours=12)

def load_data():
    data = {"users": {}, "books": {}, "sessions": {}}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
    
    data.setdefault("users", {})
    data.setdefault("books", {})
    data.setdefault("sessions", {})
    return data

def save_data(data):
    tmp_file = DB_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_file, DB_FILE)

def create_session(db, email: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + SESSION_TTL).isoformat()
    db["sessions"][token] = {"email": email, "expires_at": expires_at}
    return token

def get_current_user(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

    token = authorization.removeprefix("Bearer ").strip()

    with db_lock:
        db = load_data()
        session = db["sessions"].get(token)

        if not session:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        if datetime.now(timezone.utc) > datetime.fromisoformat(session["expires_at"]):
            del db["sessions"][token]
            save_data(db)
            raise HTTPException(status_code=401, detail="토큰이 만료되었습니다. 다시 로그인해주세요.")

        return session["email"]

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    with db_lock:
        db = load_data()
        if email in db["users"]:
            raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다.")

        db["users"][email] = pwd_context.hash(password)
        db["books"][email] = []
        save_data(db)

    return {"status": "success", "message": "회원가입이 완료되었습니다!"}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    with db_lock:
        db = load_data()
        stored_hash = db["users"].get(email)

        if not stored_hash or not pwd_context.verify(password, stored_hash):
            raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

        token = create_session(db, email)
        save_data(db)

    is_admin = email in ADMIN_EMAILS
    return {
        "status": "success",
        "message": "로그인 성공!",
        "email": email,
        "isAdmin": is_admin,
        "token": token,
    }

@app.post("/api/logout")
async def logout(authorization: str = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        with db_lock:
            db = load_data()
            db["sessions"].pop(token, None)
            save_data(db)
    return {"status": "success", "message": "로그아웃되었습니다."}

@app.post("/api/update-password")
async def update_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    email: str = Depends(get_current_user),
):
    with db_lock:
        db = load_data()
        stored_hash = db["users"].get(email)

        if not stored_hash or not pwd_context.verify(current_password, stored_hash):
            raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")

        db["users"][email] = pwd_context.hash(new_password)
        save_data(db)

    return {"status": "success", "message": "비밀번호가 성공적으로 변경되었습니다!"}

@app.get("/api/books")
async def get_books(email: str = Depends(get_current_user)):
    db = load_data()
    user_books = db["books"].get(email, [])
    return {"books": user_books}

@app.get("/api/admin/all-data")
async def get_all_data(email: str = Depends(get_current_user)):
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    db = load_data()
    all_users_info = []
    for user_email in db["users"].keys():
        user_books = db["books"].get(user_email, [])
        all_users_info.append({
            "email": user_email,
            "bookCount": len(user_books),
            "books": user_books,
        })
    return {"users": all_users_info}

@app.delete("/api/books")
async def delete_book(title: str, email: str = Depends(get_current_user)):
    with db_lock:
        db = load_data()
        user_books = db["books"].get(email, [])
        new_books = [book for book in user_books if book["title"] != title]

        if len(new_books) == len(user_books):
            raise HTTPException(status_sode=404, detail="해당 책을 찾을 수 없습니다.") if False else \
                raise_http_404() # 깔끔한 예외 처리 위해 아래처럼 수정

        db["books"][email] = new_books
        save_data(db)

    return {"status": "success", "message": f"'{title}' 책이 삭제되었습니다."}

def raise_http_404():
    raise HTTPException(status_code=404, detail="해당 책을 찾을 수 없습니다.")

def scan_book_image(image_bytes):
    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        return None
    _, encoded_img = cv2.imencode(".jpg", image)
    return encoded_img.tobytes()

@app.post("/api/upload-page")
async def upload_page(
    title: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
):
    try:
        contents = await file.read()
        processed_bytes = scan_book_image(contents)

        if processed_bytes is not None:
            base64_str = base64.b64encode(processed_bytes).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{base64_str}"
        else:
            image_url = ""

        book_info = {
            "title": title,
            "author": author,
            "image": image_url,
            "pages": [image_url],
        }

        with db_lock:
            db = load_data()
            db["books"].setdefault(email, []).append(book_info)
            save_data(db)

        return {
            "status": "success",
            "message": f"'{title}' 책이 성공적으로 등록되었습니다!",
            "book": book_info,
        }
    except Exception as e:
        print(f"업로드 에러 발생: {e}")
        raise HTTPException(status_code=500, detail="업로드 중 오류가 발생했습니다.")

@app.post("/api/add-page")
async def add_page(
    title: str = Form(...),
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
):
    try:
        contents = await file.read()
        processed_bytes = scan_book_image(contents)

        if processed_bytes is not None:
            base64_str = base64.b64encode(processed_bytes).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{base64_str}"
        else:
            image_url = ""

        with db_lock:
            db = load_data()
            user_books = db["books"].get(email, [])
            target_book = next((b for b in user_books if b["title"] == title), None)

            if not target_book:
                raise HTTPException(status_code=404, detail="해당 책을 찾을 수 없습니다.")

            if "pages" not in target_book:
                target_book["pages"] = [target_book.get("image", "")]

            target_book["pages"].append(image_url)
            save_data(db)

        return {"status": "success", "message": "페이지가 추가되었습니다!", "pages": target_book["pages"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"페이지 추가 에러 발생: {e}")
        raise HTTPException(status_code=500, detail="페이지 추가 중 오류가 발생했습니다.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
