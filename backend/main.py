from fastapi import FastAPI

app= FastAPI(title= "Self-Heal API")

@app.get("/")
def home():
    return {"message": "Self-Heal backend API is running!"}

