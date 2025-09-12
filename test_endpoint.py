from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/test-export")
async def test_export(
    limit: int = Query(10, description="Limit"),
):
    """Test endpoint."""
    return JSONResponse(
        content={
            "status": "ok",
            "limit": limit
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)