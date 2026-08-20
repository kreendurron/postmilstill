from motor.motor_asyncio import AsyncIOMotorClient
from decouple import config

# Load secrets from .env
MONGO_URI = config("MONGO_URI")
DATABASE_NAME = config("DATABASE_NAME")

try:
    # Create the client and test connection
    client = AsyncIOMotorClient(MONGO_URI)
    client.admin.command("ping")  # Ping to confirm connection
    print("MongoDB connected successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    raise

# Access the database
database = client[DATABASE_NAME]
quotes_collection = database.get_collection("quotes")
schedules_collection = database.get_collection("schedules")

def quote_helper(quote) -> dict:
    return {
        "id": str(quote["_id"]),  # Convert ObjectId to string
        "author": quote.get("author", "Unknown"),
        "text": quote.get("quote", "No quote provided"),
        "source": quote.get("source", "unknown"),  # Default to "unknown" if missing
        "link": quote.get("link", "No link provided"),  # Default if missing
    }


