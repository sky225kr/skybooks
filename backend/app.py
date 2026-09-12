from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 회원 데이터베이스 {email: password}
users_db = {}  
# 계정별 책 목록 데이터베이스 {email: [ {title, author, image}, ... ] }
books_db = {}  

# 운영자로 지정할 이메일들
ADMIN_EMAILS = ["sungkook@example.com"]  # 네 이메일로 변경 가능

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    if email in users_db:
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다.")
    users_db[email] = password
    books_db[email] = []
    return {"status": "success", "message": "회원가입이 완료되었습니다!"}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    if email not in users_db or users_db[email] != password:
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    
    is_admin = (email in ADMIN_EMAILS)
    return {"status": "success", "message": "로그인 성공!", "email": email, "isAdmin": is_admin}

@app.post("/api/update-password")
async def update_password(email: str = Form(...), current_password: str = Form(...), new_password: str = Form(...)):
    if email not in users_db or users_db[email] != current_password:
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    
    users_db[email] = new_password
    return {"status": "success", "message": "비밀번호가 성공적으로 변경되었습니다!"}

@app.get("/api/books")
async def get_books(email: str):
    user_books = books_db.get(email, [])
    return {"books": user_books}

@app.get("/api/admin/all-data")
async def get_all_data(email: str):
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    all_users_info = []
    for user_email in users_db.keys():
        user_books = books_db.get(user_email, [])
        all_users_info.append({
            "email": user_email,
            "bookCount": len(user_books),
            "books": user_books
        })
    return {"users": all_users_info}

@app.post("/api/upload-page")
async def upload_page(
    email: str = Form(...),
    title: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...)
):
    if email not in users_db:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    try:
        # 업로드된 파일을 메모리 바이트로 읽기
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        
        # OpenCV로 이미지 디코딩
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        if img is not None:
            # OpenCV 보정 처리 (가우스 블러 + 오츠 이진화)
            blurred = cv2.GaussianBlur(img, (5, 5), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_img = thresh
        else:
            # 그레이스케일 변환 실패 시 컬러로 읽어서 처리 시도
            img_color = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            processed_img = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY) if img_color is not None else nparr

        # 처리된 이미지를 메모리상에서 jpg 코딩 후 Base64로 변환
        success, encoded_img = cv2.imencode('.jpg', processed_img)
        if success:
            base64_str = base64.b64encode(encoded_img).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_str}"
        else:
            image_url = ""

        book_info = {
            "title": title,
            "author": author,
            "image": image_url
        }
        
        if email not in books_db:
            books_db[email] = []
        books_db[email].append(book_info)

        return {
            "status": "success", 
            "message": f"'{title}' 책이 성공적으로 등록 및 보정되었습니다!",
            "book": book_info
        }
    except Exception as e:
        print(f"업로드 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
