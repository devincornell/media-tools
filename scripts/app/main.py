"""
Simple FastAPI Application Template
"""
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Pydantic models for request/response validation
class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Item name")
    description: Optional[str] = Field(None, max_length=500, description="Item description")
    price: float = Field(..., gt=0, description="Item price (must be positive)")
    
class ItemCreate(ItemBase):
    pass

class ItemResponse(ItemBase):
    id: int = Field(..., description="Unique item identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class HealthCheck(BaseModel):
    status: str = "healthy"
    timestamp: datetime
    version: str = "1.0.0"

# Initialize FastAPI app
app = FastAPI(
    title="Simple FastAPI Template",
    description="A basic FastAPI application template with common patterns",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# In-memory storage (replace with database in production)
items_db = []
next_id = 1

# Dependency injection example
async def get_current_timestamp():
    return datetime.now()

# Event handlers
@app.on_event("startup")
async def startup_event():
    print("FastAPI application starting up...")
    # Initialize database connections, load config, etc.

@app.on_event("shutdown")
async def shutdown_event():
    print("FastAPI application shutting down...")
    # Clean up resources, close connections, etc.

# Exception handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found"}
    )

# API Routes
@app.get("/", response_model=dict, tags=["Root"])
async def root():
    """Root endpoint - welcome message"""
    return {
        "message": "Welcome to the Simple FastAPI Template!",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthCheck, tags=["Health"])
async def health_check(timestamp: datetime = Depends(get_current_timestamp)):
    """Health check endpoint"""
    return HealthCheck(timestamp=timestamp)

@app.get("/items", response_model=List[ItemResponse], tags=["Items"])
async def get_items(
    skip: int = 0, 
    limit: int = 100,
    search: Optional[str] = None
):
    """Get all items with optional pagination and search"""
    filtered_items = items_db
    
    # Simple search functionality
    if search:
        filtered_items = [
            item for item in items_db 
            if search.lower() in item["name"].lower() or 
               (item["description"] and search.lower() in item["description"].lower())
        ]
    
    return filtered_items[skip:skip + limit]

@app.get("/items/{item_id}", response_model=ItemResponse, tags=["Items"])
async def get_item(item_id: int):
    """Get a specific item by ID"""
    item = next((item for item in items_db if item["id"] == item_id), None)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    return item

@app.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED, tags=["Items"])
async def create_item(
    item: ItemCreate, 
    timestamp: datetime = Depends(get_current_timestamp)
):
    """Create a new item"""
    global next_id
    
    new_item = {
        "id": next_id,
        "name": item.name,
        "description": item.description,
        "price": item.price,
        "created_at": timestamp
    }
    
    items_db.append(new_item)
    next_id += 1
    
    return new_item

@app.put("/items/{item_id}", response_model=ItemResponse, tags=["Items"])
async def update_item(item_id: int, item: ItemCreate):
    """Update an existing item"""
    existing_item = next((item_data for item_data in items_db if item_data["id"] == item_id), None)
    if not existing_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    
    # Update the item
    existing_item.update({
        "name": item.name,
        "description": item.description,
        "price": item.price
    })
    
    return existing_item

@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Items"])
async def delete_item(item_id: int):
    """Delete an item"""
    global items_db
    
    item_index = next((i for i, item in enumerate(items_db) if item["id"] == item_id), None)
    if item_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    
    del items_db[item_index]
    return None

# Additional utility endpoints
@app.get("/items/stats/count", response_model=dict, tags=["Stats"])
async def get_items_count():
    """Get total count of items"""
    return {"total_items": len(items_db)}

@app.get("/items/stats/summary", response_model=dict, tags=["Stats"])
async def get_items_summary():
    """Get summary statistics of items"""
    if not items_db:
        return {
            "total_items": 0,
            "average_price": 0,
            "min_price": 0,
            "max_price": 0
        }
    
    prices = [item["price"] for item in items_db]
    return {
        "total_items": len(items_db),
        "average_price": sum(prices) / len(prices),
        "min_price": min(prices),
        "max_price": max(prices)
    }

# Development server
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
