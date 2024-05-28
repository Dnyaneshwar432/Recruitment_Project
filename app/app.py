import os
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Query
from bson import ObjectId
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient

class Candidate(BaseModel):
    email: EmailStr
    password: str
    name: str

class CandidateInDB(Candidate):
    hashed_password: str

class CandidateResponse(BaseModel):
    id: str
    email: EmailStr
    name: str

class LoginData(BaseModel):
    email: EmailStr
    password: str

class Job(BaseModel):
    title: str
    description: str
    department: str
    location: str
    employment_type: str
    salary_range: Optional[str]
    application_deadline: Optional[str]
    required_skills: List[str]
    additional_info: Optional[str]

class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    department: str
    location: str
    employment_type: str
    salary_range: Optional[str]
    application_deadline: Optional[str]
    required_skills: List[str]
    additional_info: Optional[str]



pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)



client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client['recruitment_system']



app = FastAPI()

# Root route
@app.get("/")
async def root():
    return {"message": "Welcome to the Recruitment System API"}

# Candidate signup
@app.post("/candidates/signup", response_model=CandidateResponse)
async def signup(candidate: Candidate):
    existing_candidate = await db.candidates.find_one({"email": candidate.email})
    if existing_candidate:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(candidate.password)
    candidate_in_db = CandidateInDB(**candidate.dict(), hashed_password=hashed_password)
    result = await db.candidates.insert_one(candidate_in_db.dict(exclude={"password"}))
    return CandidateResponse(id=str(result.inserted_id), email=candidate.email, name=candidate.name)

# Candidate login
@app.post("/candidates/login")
async def login(login_data: LoginData):
    candidate = await db.candidates.find_one({"email": login_data.email})
    if not candidate or not verify_password(login_data.password, candidate["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    return {"message": "Login successful"}

# Apply for job
@app.post("/jobs/{job_id}/apply")
async def apply_for_job(job_id: str, candidate_email: EmailStr):
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidate = await db.candidates.find_one({"email": candidate_email})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    await db.applications.insert_one({"job_id": ObjectId(job_id), "candidate_email": candidate_email})
    return {"message": "Job application successful"}

# Upload resume
@app.post("/candidates/{candidate_id}/resume")
async def upload_resume(candidate_id: str, file: UploadFile = File(...)):
    candidate = await db.candidates.find_one({"_id": ObjectId(candidate_id)})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Save resume file
    resume_path = f"resumes/{candidate_id}_{file.filename}"
    os.makedirs(os.path.dirname(resume_path), exist_ok=True)
    with open(resume_path, "wb") as buffer:
        buffer.write(await file.read())
    
    await db.candidates.update_one({"_id": ObjectId(candidate_id)}, {"$set": {"resume_path": resume_path}})
    return {"message": "Resume uploaded successfully"}

# Admin login
@app.post("/admin/login")
async def admin_login(login_data: LoginData):
    admin = await db.admins.find_one({"email": login_data.email})
    if not admin or not verify_password(login_data.password, admin["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    return {"message": "Admin login successful"}

# View all candidates
@app.get("/admin/candidates", response_model=List[CandidateResponse])
async def view_candidates():
    candidates = await db.candidates.find().to_list(100)
    return [CandidateResponse(id=str(candidate["_id"]), email=candidate["email"], name=candidate["name"]) for candidate in candidates]

# View all resumes
@app.get("/admin/resumes")
async def view_resumes():
    candidates = await db.candidates.find().to_list(100)
    resumes = [{"email": candidate["email"], "resume_path": candidate.get("resume_path")} for candidate in candidates if "resume_path" in candidate]
    return resumes

# View all jobs
@app.get("/jobs", response_model=List[JobResponse])
async def get_jobs():
    jobs = await db.jobs.find().to_list(100)
    return [JobResponse(id=str(job["_id"]), **job) for job in jobs]

# Get a specific job by ID
@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(id=str(job["_id"]), **job)

# Post new job
@app.post("/jobs", response_model=JobResponse)
async def post_job(job: Job):
    result = await db.jobs.insert_one(job.dict())
    return JobResponse(id=str(result.inserted_id), **job.dict())

# Update job
@app.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, job: Job):
    result = await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": job.dict()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(id=job_id, **job.dict())

# Mark job status
@app.put("/jobs/{job_id}/status")
async def update_job_status(job_id: str, status: str = Query(..., pattern="^(Open|Closed|Filled)$")):
    result = await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": f"Job status updated to {status}"}

# Fetch all candidates
@app.get("/candidates", response_model=List[CandidateResponse])
async def get_candidates():
    candidates = await db.candidates.find().to_list(100)
    return [CandidateResponse(id=str(candidate["_id"]), email=candidate["email"], name=candidate["name"]) for candidate in candidates]

# Fetch a specific candidate by ID
@app.get("/candidates/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str):
    candidate = await db.candidates.find_one({"_id": ObjectId(candidate_id)})
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateResponse(id=str(candidate["_id"]), email=candidate["email"], name=candidate["name"])

if __name__ == "__main__":
    import nest_asyncio
    import uvicorn
    nest_asyncio.apply()
    uvicorn.run(app, host="127.0.0.1", port=8089)
