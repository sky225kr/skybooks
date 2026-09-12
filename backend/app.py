from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import base64
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.json"

# 데이터 파일 불러오기 또는 초기화
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "books": {}}

# 데이터 파일 저장하기
def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

ADMIN_EMAILS = ["admin@skybooks.com"]

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    db = load_data()
    if email in db["users"]:
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다.")
    
    db["users"][email] = password
    db["books"][email] = []
    save_data(db)
    
    return {"status": "success", "message": "회원가입이 완료되었습니다!"}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    db = load_data()
    if email not in db["users"] or db["users"][email] != password:
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    
    is_admin = (email in ADMIN_EMAILS)
    return {"status": "success", "message": "로그인 성공!", "email": email, "isAdmin": is_admin}

@app.post("/api/update-password")
async def update_password(email: str = Form(...), current_password: str = Form(...), new_password: str = Form(...)):
    db = load_data()
    if email not in db["users"] or db["users"][email] != current_password:
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    
    db["users"][email] = new_password
    save_data(db)
    
    return {"status": "success", "message": "비밀번호가 성공적으로 변경되었습니다!"}

@app.get("/api/books")
async def get_books(email: str):
    db = load_data()
    user_books = db["books"].get(email, [])
    return {"books": user_books}

@app.get("/api/admin/all-data")
async def get_all_data(email: str):
    db = load_data()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    all_users_info = []
    for user_email in db["users"].keys():
        user_books = db["books"].get(user_email, [])
        all_users_info.append({
            "email": user_email,
            "bookCount": len(user_books),
            "books": user_books
        })
    return {"users": all_users_info}

@app.delete("/api/books")
async def delete_book(email: str = Form(...), title: str = Form(...)):
    db = load_data()
    if email not in db["users"]:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
    
    user_books = db["books"].get(email, [])
    # 일치하는 제목을 가진 책을 제외하고 남김
    new_books = [book for book in user_books if book["title"] != title]
    
    if len(new_books) == len(user_books):
        raise HTTPException(status_code=404, detail="해당 책을 찾을 수 없습니다.")
    
    db["books"][email] = new_books
    save_data(db)
    
    return {"status": "success", "message": f"'{title}' 책이 삭제되었습니다."}


@app.post("/api/upload-page")
async def upload_page(
    email: str = Form(...),
    title: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...)
):
    db = load_data()
    if email not in db["users"]:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        
        # 흑백으로 강제 변환하지 않고 컬러 원본(IMREAD_COLOR)으로 읽어옵니다.
        img_color = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_color is not None:
            # 컬러 이미지를 그대로 JPEG로 인코딩
            success, encoded_img = cv2.imencode('.jpg', img_color)
            if success:
                base64_str = base64.b64encode(encoded_img).decode('utf-8')
                image_url = f"data:image/jpeg;base64,{base64_str}"
            else:
                image_url = ""
        else:
            image_url = ""

        book_info = {
            "title": title,
            "author": author,
            "image": image_url
        }
        
        if email not in db["books"]:
            db["books"][email] = []
        db["books"][email].append(book_info)
        
        save_data(db)

        return {
            "status": "success", 
            "message": f"'{title}' 책이 성공적으로 등록되었습니다!",
            "book": book_info
        }
    except Exception as e:
        print(f"업로드 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
