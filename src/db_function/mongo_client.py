import os
import datetime
import motor.motor_asyncio
from src.log import setup_logger

log = setup_logger(__name__)

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "wfreedom")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "tweets")

# Initialize motor client
try:
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]
    tweets_collection = db[MONGO_COLLECTION]
except Exception as e:
    log.error(f"Failed to initialize MongoDB client: {e}")
    tweets_collection = None

async def save_tweet_to_mongo(tweet, username: str, channel_ids: list = None):
    """
    Saves a tweet object to MongoDB asynchronously.
    """
    if tweets_collection is None:
        log.warning("MongoDB is not configured or failed to initialize. Skipping tweet save.")
        return

    try:
        media_urls = []
        if tweet.media:
            for item in tweet.media:
                media_urls.append({
                    "type": getattr(item, "type", ""),
                    "url": getattr(item, "media_url_https", "") or getattr(item, "expanded_url", "")
                })

        tweet_doc = {
            "tweet_id": tweet.id,
            "username": username,
            "author_id": getattr(tweet.author, "id", None) if tweet.author else None,
            "author_name": getattr(tweet.author, "name", "") if tweet.author else "",
            "text": tweet.text,
            "url": tweet.url,
            "created_on": tweet.created_on,
            "media": media_urls,
            "channel_ids": channel_ids or [],
            "is_retweet": tweet.is_retweet,
            "saved_at": datetime.datetime.now(datetime.timezone.utc)
        }

        # Use update_one with upsert to avoid duplicates if the same tweet is fetched again
        await tweets_collection.update_one(
            {"tweet_id": tweet.id},
            {"$set": tweet_doc},
            upsert=True
        )
        log.info(f"Successfully saved tweet {tweet.id} to MongoDB")
    except Exception as e:
        log.error(f"Failed to save tweet to MongoDB: {e}")
