from app.utils.seeder import seed_data
import asyncio

if __name__ == "__main__":
    asyncio.run(seed_data(num_users=50, share=30, blogs_per_user=20))
